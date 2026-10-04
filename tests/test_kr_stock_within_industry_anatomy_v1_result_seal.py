"""Result seal for kr-stock-within-industry-anatomy-v1: exact artifact bytes, exact identities, no recomputation, no re-execution."""
import ast
import gzip
import hashlib
import json
from pathlib import Path

import pytest
from pipeline import kr_stock_within_industry_anatomy as S
from pipeline import kr_stock_within_industry_anatomy_execution as E

ROOT = Path(__file__).resolve().parents[1]
R = ROOT / "docs/results"
P = "kr-stock-within-industry-anatomy-v1-"
RESULT, MANIFEST, MARKER, PROV, REPORT = (R / (P + n) for n in ("result.json", "manifest.json", "execution-started.json", "seal-provenance.json", "report.md"))
TABLES = ROOT / "data/kr-stock-within-industry-anatomy-v1/tables"
ARCHIVE = "98b51e1d0fe6746d06dae49aad694ab341ffb12dbf2c4161f98d057bda06da8c"
SPEC = "cfcec648194e25a8914056266443e241528a68352054a10d75cb6889225e5073"
INPUT = "233df37ed205cc6b48828121e711417ccf961301dc58aa252430b343db9666a7"
RESULT_SHA = "3862c390a52f6f19abaa7849e41620858cd154735136647ee36c958624c2739f"
MANIFEST_SHA = "b458ca96c4db70dc6b9ae01d4d9181f238e1a63ffb95e98179e83bb1941cf30b"
MARKER_SHA = "81e81c1e8b060bd5c3cf6b83e07523352bbfd48cdb8cbd422e8b12978b96a5b1"
STATUS = "EXPLORATORY_DEVELOPMENT_ON_OUTCOME_EXPOSED_KR_HISTORY"
MAIN_SHA = "76c5b48d95806f7e27d3602ac205103d3c0c4ee6"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


@pytest.fixture(scope="module")
def prov():
    return json.loads(PROV.read_text())


@pytest.fixture(scope="module")
def result():
    return json.loads(RESULT.read_text())


def test_committed_result_files_are_pinned_byte_for_byte(prov):
    assert (sha(RESULT), sha(MANIFEST), sha(MARKER)) == (RESULT_SHA, MANIFEST_SHA, MARKER_SHA)
    files = prov["committedFiles"]
    for path in (RESULT, MANIFEST, MARKER):
        entry = files["docs/results/" + path.name]
        assert entry["sha256"] == sha(path) and entry["bytes"] == path.stat().st_size
    assert {v["sourceFile"] for v in files.values()} == {"stock-within-industry-anatomy.json", "manifest.json", "execution-started.json"}


def test_tables_match_the_manifest_and_provenance(prov):
    manifest = json.loads(MANIFEST.read_text())
    tables = {k: v for k, v in manifest["files"].items() if k.startswith("tables/")}
    assert len(tables) == 2 and manifest["files"]["stock-within-industry-anatomy.json"] == RESULT_SHA
    for name, wanted in tables.items():
        assert sha(TABLES / Path(name).name) == wanted
    assert {Path(k).name: v["sha256"] for k, v in prov["committedTables"].items()} == {Path(k).name: v for k, v in tables.items()}
    assert set(Path(k).name for k in tables) == {"full.csv.gz", "exclude_samsung_electronics_and_sk_hynix.csv.gz"}


def test_execution_run_and_artifact_identity_are_pinned(prov):
    assert (prov["executionRunId"], prov["artifactId"], prov["artifactName"]) == (37196246044, 11300998906, "kr-stock-within-industry-anatomy-v1-results-37196246044")
    assert prov["artifactArchiveSha256"] == ARCHIVE and prov["executionSha"] == MAIN_SHA
    assert prov["specSha256"] == SPEC and prov["inputIdentitySha256"] == INPUT and prov["statisticsRecomputed"] is False
    assert prov["sealedAtUtc"].endswith("Z") and prov["scientificStatus"] == STATUS


def test_execution_lock_evidence_is_recorded(prov):
    refs = {r["ref"]: r["sha"] for r in prov["executionLock"]["observedRefs"]}
    assert refs == {"refs/tags/kr-stock-within-industry-anatomy-v1-execution-lock": MAIN_SHA,
                    "refs/tags/kr-stock-within-industry-anatomy-v1-execution-lock-" + SPEC: MAIN_SHA}
    marker = json.loads(MARKER.read_text())
    assert marker["lockRef"] == "refs/tags/kr-stock-within-industry-anatomy-v1-execution-lock-" + SPEC and marker["lockedMainSha"] == MAIN_SHA
    assert marker["outcomesReadBeforeThisMarker"] == 0 and marker["specSha256"] == SPEC and marker["inputIdentitySha256"] == INPUT


def test_frozen_spec_and_membership_remain_exact():
    spec, sha_ = E.load_spec(ROOT)  # also re-verifies import closure, harness hashes, membership, feature and prior-sealed pins
    assert sha_ == SPEC == (ROOT / "research_specs/kr-stock-within-industry-anatomy-v1.sha256").read_text().strip()
    assert spec["scientificStatus"] == STATUS and spec["input"]["identitySha256"] == INPUT
    assert spec["membership"]["v4Decision"] == "DATA_FOUNDATION_INSUFFICIENT_V4"
    assert spec["boundary"]["outcomeExecutionInThisChange"] is False  # the frozen protocol text is unchanged by the seal


def test_status_benchmark_return_basis_and_counters_are_unchanged(result):
    manifest = json.loads(MANIFEST.read_text())
    assert result["scientificStatus"] == manifest["scientificStatus"] == STATUS
    assert result["returnBasis"] == manifest["returnBasis"] == "BENCHMARK_RELATIVE_ADJUSTED_INDEX_RETURN_PARTIAL_DISTRIBUTIONS"
    assert result["benchmark"] == "069500.KS" and result["studyId"] == manifest["studyId"] == "kr-stock-within-industry-anatomy-v1"
    assert manifest["counters"] == {"analysisCalls": 1, "labelCalls": 219600, "markerWrites": 1, "outcomeColumnCalls": 219600, "priorResultReads": 1, "targetCalls": 219600}
    S.assert_no_forbidden_keys(result)
    text = REPORT.read_text()
    assert "neither a price return nor a total shareholder return" in text and "not production-ready" in text and "not predictive" in text
    assert not any(t in text for t in ("recommended portfolio", "is production-ready", "is validated", "PASS ", "FAIL ", "best feature"))


def test_result_structure_covers_every_registered_cell_without_selection(result):
    a = result["analysis"]
    assert set(a) == set(S.SENSITIVITIES) and sorted(result["signViews"]) == sorted(S.FEATURES)
    for sens in a.values():
        assert {k.split("|")[0] for k in sens["pooledIc"]} == set(S.FEATURES)
        assert {tuple(k.split("|")[1:5]) for k in sens["pooledIc"]} == {(fl, c, lens, f"H{h}") for fl in S.FEATURE_LENSES for c in S.COMPONENTS
                                                                         for lens in S.WEIGHT_LENSES for h in S.HORIZONS}
        assert len(sens["pooledIc"]) == 11 * 2 * 3 * 2 * 3 and len(sens["coverage"]) == 11 * 2 * 3
    assert set(result["questions"]) == set(S.QUESTIONS) and len(result["priorComparison"]) == 11 * 2
    assert result["analysis"]["FULL"]["pooledIc"]["bookToMarketProxy|WITHIN_INDUSTRY_RANK|STOCK_MINUS_LOO_INDUSTRY|CAP_WEIGHTED|H126"]["validDates"] == 518


def test_eligibility_equals_the_pre_execution_membership_audit_and_keeps_denominators(result):
    readiness = json.loads((R / (P + "readiness.json")).read_text())["membershipOnlyEligibility"]
    for name in S.SENSITIVITIES:
        sealed, audited = result["eligibility"][name], readiness[name]
        assert sealed["byStatus"] == audited["byStatus"] and sealed["stockDates"] == audited["stockDates"] == 73200
        assert sealed["unknownRetainedInDenominator"] == 3442 and sum(sealed["byStatus"].values()) == 73200


def test_report_is_exactly_the_rendering_of_the_committed_result(result):
    from scripts import render_kr_stock_within_industry_anatomy_v1_report as report
    assert REPORT.read_text() == report.render(result)
    text = REPORT.read_text()
    for feature in S.FEATURES:
        assert feature in text  # every registered feature is reported, favourable or not
    for sensitivity in S.SENSITIVITIES:
        assert sensitivity in text
    for needle in ("A sealed stock−market", "A' same-sample stock−market", "stock−LOO industry", "H252", "BENCHMARK", "## 9. Observed", "## 10. Hypotheses", "## 11. Not established"):
        assert needle.replace("BENCHMARK", "state 0.4") in text


def test_headline_numbers_in_the_report_equal_the_sealed_result(result):
    a, c = result["analysis"]["FULL"], result["priorComparison"]
    within = lambda f: a["pooledIc"][f"{f}|WITHIN_INDUSTRY_RANK|STOCK_MINUS_LOO_INDUSTRY|CAP_WEIGHTED|H126"]  # noqa: E731
    assert round(within("bookToMarketProxy")["mean"], 3) == 0.086 and round(within("earningsYieldProxy")["mean"], 3) == 0.073
    assert round(within("negativeDownsideVol126")["mean"], 3) == 0.062 and round(within("logAdv60")["mean"], 3) == 0.041
    assert round(c["bookToMarketProxy|H126"]["sealedStockMinusMarket"], 3) == 0.097
    assert c["bookToMarketProxy|H126"]["shiftVersusSealed"]["shiftClass"] == "SURVIVES"
    assert {f for f, v in result["signViews"].items() if v["label"] == "SIGN_DEPENDS_ON_VIEW"} == {
        "momentum121", "negativeAccrualsToAssets", "negativeDownsideVol126", "ocfToAssets", "relative126"}
    assert {f for f, v in result["signViews"].items() if v["label"] == "POSITIVE_IN_ALL_REGISTERED_VIEWS"} == {
        "bookToMarketProxy", "earningsYieldProxy", "logAdv60", "netIncomeToAssets", "ocfImprovementToAssets", "ocfYieldProxy"}
    # the hypotheses in the report rest on exactly these facts
    assert c["ocfToAssets|H252"]["shiftVersusSameSample"]["shiftClass"] == "CHANGES_SIGN"
    assert not [f for f in S.FEATURES if c[f + "|H126"]["shiftVersusSealed"]["shiftClass"] == "CHANGES_SIGN"]


def test_the_seal_blocks_re_execution_and_leaves_no_sealing_path():
    assert E.RESULT_PATH == "docs/results/kr-stock-within-industry-anatomy-v1-result.json" and RESULT.exists() and MARKER.exists()
    assert not (ROOT / ".github/seal").exists()
    assert not (ROOT / ".github/workflows/seal-kr-stock-within-industry-anatomy-v1.yml").exists()
    spec, sha_ = E.load_spec(ROOT)
    env = {"GITHUB_ACTIONS": "true", "GITHUB_REF": "refs/heads/main", "GITHUB_EVENT_NAME": "workflow_dispatch", "GITHUB_SHA": "x",
           "ANATOMY_INPUT_ARTIFACT": spec["input"]["artifactName"], "ANATOMY_INPUT_RUN_ID": str(spec["input"]["producingRunId"])}

    def git(args, root):
        return b"x" if args[:1] == ["rev-parse"] else (Path(root) / args[1].split(":", 1)[1]).read_bytes()
    with pytest.raises(ValueError, match="RESULT_ALREADY_COMMITTED"):
        E.authorize_execution(spec, sha_, root=ROOT, env=env, git=git, lock_probe=lambda: False)


def test_no_prior_sealed_study_is_modified():
    anatomy = json.loads((R / "kr-factor-anatomy-v1-seal-provenance.json").read_text())
    assert anatomy["artifactArchiveSha256"] == "f8020bdac9878f523091881d129e3c414234012c17e1fd61e1e49b6d6538b80f"
    assert sha(R / "kr-factor-anatomy-v1-result.json") == anatomy["committedFiles"]["docs/results/kr-factor-anatomy-v1-result.json"]["sha256"]
    industry = json.loads((R / "kr-industry-opportunity-anatomy-v1-seal-provenance.json").read_text())
    assert sha(R / "kr-industry-opportunity-anatomy-v1-result.json") == industry["committedFiles"]["docs/results/kr-industry-opportunity-anatomy-v1-result.json"]["sha256"]
    assert (ROOT / "research_specs/kr-model-overlay-portfolio-v1.sha256").read_text().strip() == "563b64ee6f4709a263719669f795ad55e7828e340f082358af1599453253b6fd"
    assert (ROOT / "research_specs/kr-industry-opportunity-anatomy-v1.sha256").read_text().strip() == "98278ce5724b27dd19d253eab6cb1e7854ea432a62098441cdad46d067609f55"
    v4 = json.loads(gzip.decompress((ROOT / "data/kr-industry-membership-foundation-v4/state/audit.json.gz").read_bytes()))
    assert v4["decision"] == "DATA_FOUNDATION_INSUFFICIENT_V4"
    spec, _ = E.load_spec(ROOT)
    for rel, wanted in spec["priorSealed"]["resultFiles"].items():
        assert sha(ROOT / rel) == wanted


def test_the_seal_scripts_never_call_an_analysis_or_outcome_function():
    for module in ("scripts/render_kr_stock_within_industry_anatomy_v1_report.py",):
        tree = ast.parse((ROOT / module).read_text())
        imported = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)} | {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
        assert not any(m and ("pipeline" in m or "kr_stock_within_industry" in m or "prices" in m) for m in imported)
