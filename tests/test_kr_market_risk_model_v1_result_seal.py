"""kr-market-risk-model-v1 result seal. Before the one-shot execution nothing may be sealed (all four files absent together). Once the automatic Draft
seal has been merged, the committed bytes must equal the provenance record and carry this spec, the locked commit and the marker order. Nothing here
computes an outcome."""
import hashlib
import json
from pathlib import Path

from pipeline import kr_market_risk_model_execution as E
from pipeline import kr_market_risk_model_seal as SEAL

ROOT = Path(__file__).resolve().parents[1]
FILES = [ROOT / rel for rel in SEAL.COMMITTED.values()] + [ROOT / SEAL.PROVENANCE_PATH]


def test_seal_files_exist_all_together_or_not_at_all():
    assert len({p.exists() for p in FILES}) == 1
    assert SEAL.COMMITTED["market-risk-model.json"] == E.RESULT_PATH and SEAL.COMMITTED["execution-started.json"] == E.MARKER_PATH
    assert SEAL.COMMITTED["manifest.json"] == E.MANIFEST_PATH and set(SEAL.ARTIFACT_FILES) == set(E.ARTIFACT_FILES)
    assert SEAL.LOCK_PREFIX == E.LOCK_PREFIX and SEAL.STUDY == E.STUDY


def test_a_committed_seal_is_the_exact_formal_artifact():
    if not FILES[0].exists():
        return                                                                    # PREREGISTRATION ONLY: no outcome exists yet
    record = SEAL.verify_written(ROOT)
    files = {name: (ROOT / rel).read_bytes() for name, rel in SEAL.COMMITTED.items()}
    sha = (ROOT / "research_specs/kr-market-risk-model-v1.sha256").read_text().strip()
    SEAL.verify_bundle(files, sha, record["executionSha"])
    assert record["specSha256"] == sha and record["artifactArchiveSha256"] == record["artifactGithubDigest"][len("sha256:"):]
    assert all(hashlib.sha256(files[e["sourceFile"]]).hexdigest() == e["sha256"] for e in record["committedFiles"].values())
    assert json.loads(files["market-risk-model.json"])["scientificStatus"] == "EXPLORATORY_DEVELOPMENT_ON_OUTCOME_EXPOSED_KR_HISTORY"
