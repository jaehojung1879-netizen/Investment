"""Result seal for kr-industry-opportunity-anatomy-v1: exact artifact bytes, exact identities, no recomputation, no re-execution."""
import ast
import gzip
import hashlib
import json
from pathlib import Path

import pytest
from pipeline import kr_industry_anatomy as I
from pipeline import kr_industry_anatomy_execution as E

ROOT = Path(__file__).resolve().parents[1]
R = ROOT / "docs/results"
P = "kr-industry-opportunity-anatomy-v1-"
RESULT, MANIFEST, MARKER, PROV, REPORT = (R / (P + n) for n in ("result.json", "manifest.json", "execution-started.json", "seal-provenance.json", "report.md"))
TABLES = ROOT / "data/kr-industry-opportunity-anatomy-v1/tables"
ARCHIVE = "ee336dc4ff51cbef21f3f8adbb780c5987e93525d677cdc7bdb5a7dd5400f4ba"
SPEC = "98278ce5724b27dd19d253eab6cb1e7854ea432a62098441cdad46d067609f55"
INPUT = "233df37ed205cc6b48828121e711417ccf961301dc58aa252430b343db9666a7"
RESULT_SHA = "71a960e3c19ce443d058508c4ec66576e3e5fcbd7a45dc851cf8b832bff62a08"
MANIFEST_SHA = "b8814d43f2e592fea0db7b7e4e7d77485f04881140dc46a197610086383621df"
MARKER_SHA = "414911b0ebb340332bbfe0340428f40959bc3fbc73b23cb2c2f92a30390f3bfb"
STATUS = "EXPLORATORY_DEVELOPMENT_ON_PARTIALLY_RECONSTRUCTED_KR_HISTORY"
MAIN_SHA = "f830b92efabab6011f9190293f2e060e9b4fe70b"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


@pytest.fixture(scope="module")
def prov():
    return json.loads(PROV.read_text())


def test_committed_result_files_are_pinned_byte_for_byte(prov):
    assert (sha(RESULT), sha(MANIFEST), sha(MARKER)) == (RESULT_SHA, MANIFEST_SHA, MARKER_SHA)
    files = prov["committedFiles"]
    for path in (RESULT, MANIFEST, MARKER):
        entry = files["docs/results/" + path.name]
        assert entry["sha256"] == sha(path) and entry["bytes"] == path.stat().st_size
    assert {v["sourceFile"] for v in files.values()} == {"industry-anatomy.json", "manifest.json", "execution-started.json"}


def test_tables_match_the_manifest_and_provenance(prov):
    manifest = json.loads(MANIFEST.read_text())
    tables = {k: v for k, v in manifest["files"].items() if k.startswith("tables/")}
    assert len(tables) == 3 and manifest["files"]["industry-anatomy.json"] == RESULT_SHA
    for name, wanted in tables.items():
        assert sha(TABLES / Path(name).name) == wanted
    assert {Path(k).name: v["sha256"] for k, v in prov["committedTables"].items()} == {Path(k).name: v for k, v in tables.items()}


def test_execution_run_and_artifact_identity_are_pinned(prov):
    assert (prov["executionRunId"], prov["artifactId"], prov["artifactName"]) == (37182657697, 11295658265, "kr-industry-opportunity-anatomy-v1-results-37182657697")
    assert prov["artifactArchiveSha256"] == ARCHIVE and prov["executionSha"] == MAIN_SHA
    assert prov["specSha256"] == SPEC and prov["inputIdentitySha256"] == INPUT and prov["statisticsRecomputed"] is False
    assert prov["sealedAtUtc"].endswith("Z")


def test_execution_lock_evidence_is_recorded(prov):
    refs = {r["ref"]: r["sha"] for r in prov["executionLock"]["observedRefs"]}
    assert refs == {"refs/tags/kr-industry-opportunity-anatomy-v1-execution-lock": MAIN_SHA,
                    "refs/tags/kr-industry-opportunity-anatomy-v1-execution-lock-" + SPEC: MAIN_SHA}
    marker = json.loads(MARKER.read_text())
    assert marker["lockRef"] == "refs/tags/kr-industry-opportunity-anatomy-v1-execution-lock-" + SPEC and marker["lockedMainSha"] == MAIN_SHA
    assert marker["outcomesReadBeforeThisMarker"] == 0 and marker["specSha256"] == SPEC


def test_frozen_spec_and_membership_remain_exact():
    spec, sha_ = E.load_spec(ROOT)  # also re-verifies import closure, harness hashes and membership pins
    assert sha_ == SPEC == (ROOT / "research_specs/kr-industry-opportunity-anatomy-v1.sha256").read_text().strip()
    assert spec["scientificStatus"] == STATUS and spec["input"]["identitySha256"] == INPUT
    assert spec["membership"]["v4Decision"] == "DATA_FOUNDATION_INSUFFICIENT_V4"


def test_status_benchmark_and_return_basis_are_unchanged():
    result, manifest = json.loads(RESULT.read_text()), json.loads(MANIFEST.read_text())
    assert result["scientificStatus"] == manifest["scientificStatus"] == STATUS
    assert result["returnBasis"] == manifest["returnBasis"] == "BENCHMARK_RELATIVE_ADJUSTED_INDEX_RETURN_PARTIAL_DISTRIBUTIONS"
    assert result["benchmark"] == "069500.KS" and result["studyId"] == manifest["studyId"] == "kr-industry-opportunity-anatomy-v1"
    I.assert_no_forbidden_keys(result)
    text = REPORT.read_text()
    assert "not total shareholder return" in text and "does NOT establish prospective predictability" in text
    assert "not production-ready" in text and not any(t in text for t in ("PROMOTION", "recommended portfolio", "is production-ready", "PASS ", "FAIL "))


def test_result_structure_covers_every_registered_cell_without_selection():
    a = json.loads(RESULT.read_text())["analysis"]
    assert set(a) == set(I.SENSITIVITIES)
    for sens in a.values():
        assert {k.split("|")[0] for k in sens["ic"]} == set(I.FEATURES)
        assert {(k.split("|")[1], k.split("|")[2]) for k in sens["ic"]} == {(lens, f"H{h}") for lens in I.LENSES for h in I.HORIZONS}
    assert a["FULL"]["ic"]["REL_MOM_126|CAP_WEIGHTED|H126"]["validDates"] == 404


def test_report_is_exactly_the_rendering_of_the_committed_result():
    from scripts import render_kr_industry_anatomy_v1_report as report
    assert REPORT.read_text() == report.render(json.loads(RESULT.read_text()))
    text = REPORT.read_text()
    for feature in I.FEATURES:
        assert feature in text  # every registered feature is reported, favourable or not


def test_headline_numbers_in_the_report_equal_the_sealed_result():
    a = json.loads(RESULT.read_text())["analysis"]["FULL"]
    ic = a["ic"]["REL_MOM_126|CAP_WEIGHTED|H126"]
    ter = a["tercile"]["MEDIAN_netIncomeImprovementToAssets|CAP_WEIGHTED|H126"]
    assert round(ic["mean"], 3) == 0.066 and round(a["tercile"]["REL_MOM_126|CAP_WEIGHTED|H126"]["mean"] * 100, 1) == 5.4
    assert round(ter["mean"] * 100, 1) == -10.1 and round(a["ic"]["MEDIAN_bookToMarketProxy|CAP_WEIGHTED|H126"]["mean"], 3) == -0.059


def test_the_seal_blocks_re_execution_and_leaves_no_sealing_path():
    assert E.RESULT_PATH == "docs/results/kr-industry-opportunity-anatomy-v1-result.json" and RESULT.exists() and MARKER.exists()
    assert not (ROOT / ".github/seal").exists()
    assert not (ROOT / ".github/workflows/seal-kr-industry-opportunity-anatomy-v1.yml").exists()
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
    assert (ROOT / "research_specs/kr-model-overlay-portfolio-v1.sha256").read_text().strip() == "563b64ee6f4709a263719669f795ad55e7828e340f082358af1599453253b6fd"
    v4 = json.loads(gzip.decompress((ROOT / "data/kr-industry-membership-foundation-v4/state/audit.json.gz").read_bytes()))
    assert v4["decision"] == "DATA_FOUNDATION_INSUFFICIENT_V4"


def test_the_seal_scripts_never_call_an_analysis_or_outcome_function():
    for module in ("scripts/render_kr_industry_anatomy_v1_report.py",):
        tree = ast.parse((ROOT / module).read_text())
        imported = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)} | {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
        assert not any(m and ("pipeline" in m or "kr_industry_anatomy" in m or "prices" in m) for m in imported)
