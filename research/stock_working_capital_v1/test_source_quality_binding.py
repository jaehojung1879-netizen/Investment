"""Synthetic input receipts and fake acquisition metadata; no HTTP or outcomes."""
from copy import deepcopy
import gzip
import json

import pytest

from . import age_policy as AP
from . import features as F
from . import pit_admission as A
from . import pit_filing_evidence as E
from . import pit_join as J
from . import portable_collection as P
from . import source_quality as Q
from .test_pit_admission import worker


def acquisition(tmp_path, mutate=None):
    directory = tmp_path / "acquisition"
    directory.mkdir()
    manifest = json.loads((P.HERE / "xbrl_recovery_v2/acquisition/manifest.json").read_text())
    if mutate:
        mutate(manifest)
    raw = (json.dumps(manifest, sort_keys=True, indent=2) + "\n").encode()
    (directory / "manifest.json").write_bytes(raw)
    return directory, E.sha(raw)


def measurement(tmp_path, manifest_sha, *, positive=False):
    directory = tmp_path / "measurement"
    directory.mkdir()
    w = worker(real_packages=positive)
    w.fiscal_age_policy = AP.pending_policy()
    cohort, rows = w.on("2025-03-21")
    report = {"coverage": A.coverage([cohort], rows), "outputSha256": {},
              "fiscalAgePolicy": AP.pending_policy(), "historicalReturnLabelsRead": 0,
              "historicalReturnCalculations": 0, "modelFits": 0}
    if manifest_sha is not None:
        report["originalRecoveryManifestSha256"] = manifest_sha
    for name, values in (("cohorts.jsonl.gz", [cohort]), ("rows.jsonl.gz", rows)):
        raw = gzip.compress(J.canonical_lines(values), mtime=0)
        (directory / name).write_bytes(raw)
        report["outputSha256"][name] = E.sha(raw)
    (directory / "coverage.json").write_text(json.dumps(report))
    assert J.verify_measurement(directory)["memberDates"] == 3
    return directory


def test_positive_measurement_cannot_be_attributed_to_another_acquisition(tmp_path):
    acquired, _ = acquisition(tmp_path)
    measured = measurement(tmp_path, "f" * 64, positive=True)
    output = tmp_path / "report.json"
    with pytest.raises(ValueError, match="MEASUREMENT_ACQUISITION"):
        Q.write_report(measured, acquired, output)
    assert not output.exists()


def test_acquisition_binding_is_required_even_when_all_inputs_are_blocked(tmp_path):
    acquired, _ = acquisition(tmp_path)
    measured = measurement(tmp_path, None)
    with pytest.raises(ValueError, match="MEASUREMENT_ACQUISITION"):
        Q.write_report(measured, acquired, tmp_path / "report.json")


@pytest.mark.parametrize("kind", ["duplicate", "missing", "foreign", "issuer", "fiscal", "counts", "calls"])
def test_manifest_partition_and_fixed_target_identity_are_verified(tmp_path, kind):
    def mutate(manifest):
        if kind == "duplicate":
            manifest["rows"][1] = deepcopy(manifest["rows"][0])
        elif kind == "missing":
            manifest["rows"].pop()
        elif kind == "foreign":
            manifest["rows"][0]["receipt"] = "19990101000001"
        elif kind == "issuer":
            manifest["rows"][0]["corpCode"] = "99999999"
        elif kind == "fiscal":
            manifest["rows"][0]["fiscalYear"] += 1
        elif kind == "counts":
            manifest["statusCounts"] = {"ACQUIRED_UNVERIFIED_ORIGINAL_XBRL_ZIP": 68}
        else:
            manifest["publicRequestsAttempted"] = True
    acquired, sha = acquisition(tmp_path, mutate)
    measured = measurement(tmp_path, sha)
    with pytest.raises(ValueError):
        Q.write_report(measured, acquired, tmp_path / "report.json")


def test_acquired_status_without_original_object_provenance_is_not_counted(tmp_path):
    def mutate(manifest):
        manifest["rows"][0]["status"] = "ACQUIRED_UNVERIFIED_ORIGINAL_XBRL_ZIP"
        manifest["statusCounts"] = {"ACQUIRED_UNVERIFIED_ORIGINAL_XBRL_ZIP": 1,
                                   "NOT_ATTEMPTED_ENVIRONMENT_NETWORK_BLOCKED": 67}
        manifest["publicRequestsAttempted"] = 2
    acquired, sha = acquisition(tmp_path, mutate)
    measured = measurement(tmp_path, sha)
    with pytest.raises(ValueError):
        Q.write_report(measured, acquired, tmp_path / "report.json")


def test_bound_blocked_partition_still_reports_all_68_and_preserves_denominator(tmp_path):
    acquired, sha = acquisition(tmp_path)
    measured = measurement(tmp_path, sha)
    output = tmp_path / "report.json"
    result = Q.write_report(measured, acquired, output)
    assert result["fixedOriginalTargets"] == 68
    assert result["originalPackagesAcquiredUnverified"] == 0
    for signal in F.SIGNALS:
        assert result["signals"][signal]["denominator"] == 3
        assert result["signals"][signal]["originalFinancialFactsVerifiedPairs"] == 0
        assert sum(result["signals"][signal]["exclusiveFirstUnresolvedStage"].values()) == 3
    original = output.read_bytes()
    with pytest.raises(ValueError, match="PRESERVE_PREVIOUS"):
        Q.write_report(measured, acquired, output)
    assert output.read_bytes() == original
