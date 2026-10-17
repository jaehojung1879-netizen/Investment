"""rp1-c1 WP4d: workflow route, storage rule, source freeze, owner authorization, one-shot lock, validator and report.

Synthetic data only. The end-to-end test builds bounded synthetic inputs through the REAL acquirer (fake transport),
freezes hashes and re-fetches them in a throwaway copy of the repository, authorizes it, and runs the formal execution against a fake
GitHub API. It never touches a vendor, the real repository's files or a real lock."""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import subprocess

import numpy as np
import pandas as pd
import pytest

from pipeline import kr_market_risk_model as K
from pipeline import kr_market_risk_model_execution as E
from pipeline import rp1_c1_us_execution as X
from pipeline import rp1_c1_us_exposure as U
from pipeline import rp1_c1_us_exposure_spec as SP
from pipeline import rp1_c1_us_sources as SRC
from pipeline import rp1_c1_us_validator as V
from pipeline import rp1_c1_us_refetch as R

ROOT = Path(__file__).resolve().parents[1]
HOST = ROOT / X.HOST_WORKFLOW


def load_script(name, rel):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def git_show_main(rel):
    try:
        return subprocess.run(["git", "show", "origin/main:" + rel], capture_output=True, text=True, cwd=ROOT, check=True).stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        pytest.skip("no git history available")


# =======================================================================================================================================
# The route lives in an existing, unpinned workflow; the census and every sealed file are untouched
# =======================================================================================================================================
def job_block(text, name):
    start = text.index(f"\n  {name}:\n") + 1
    nxt = re.search(r"\n  [a-z0-9][a-z0-9-]*:\n", text[start + 3:])
    return text[start:start + 3 + nxt.start()] if nxt else text[start:]


def test_the_host_is_an_existing_workflow_no_sealed_spec_pins():
    pinned = set()
    for path in list((ROOT / "research_specs").glob("*.json")) + list((ROOT / "docs/research-program/specs").glob("*.json")):
        document = json.loads(path.read_text())
        pinned |= set((document.get("dependencyHashes") or {}).keys()) if isinstance(document, dict) else set()
    assert X.HOST_WORKFLOW not in pinned
    old = git_show_main(X.HOST_WORKFLOW)
    old_hash = hashlib.sha256(old.encode()).hexdigest()
    for path in list((ROOT / "research_specs").glob("*")) + list((ROOT / "docs/results").glob("*")):
        if path.is_file() and path.suffix in (".json", ".sha256", ".md"):
            assert old_hash not in path.read_text(errors="ignore")


def test_no_new_workflow_file_and_the_census_and_its_pinned_layers_are_untouched():
    try:
        diff = subprocess.run(["git", "diff", "--name-only", "origin/main...HEAD"], capture_output=True, text=True, cwd=ROOT, check=True).stdout.split()
        status = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True, cwd=ROOT, check=True).stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        pytest.skip("no git history available")
    touched = set(diff) | {line[3:] for line in status.splitlines()}
    protected = {"tests/test_workflow_inventory.py", "tests/test_kr_alpha_atlas_price_repair_workflow_inventory.py", "docs/workflow-inventory.md",
                 "docs/workflow-inventory-addendum.md", "docs/workflow-inventory-phase-c-amendment.md", "docs/workflow-inventory-phase-c-price-repair.md"}
    assert not touched & protected
    assert not [p for p in touched if p.startswith((".github/workflows/",)) and p != X.HOST_WORKFLOW]
    assert not [p for p in touched if p.startswith(("research_specs/", "docs/results/", "ledger/", "data/"))]


def test_the_original_seal_job_is_unchanged_except_its_guard():
    old, new = git_show_main(X.HOST_WORKFLOW), HOST.read_text()
    if "rp1-c1-execute" in old:
        pytest.skip("the route is already on main")
    before, after = job_block(old, "seal"), job_block(new, "seal")
    guard = "    if: github.event_name == 'workflow_dispatch' && inputs.rp1_c1_action == 'none'\n"
    assert after == before.replace("  seal:\n", "  seal:\n" + guard, 1)


def test_each_route_job_runs_only_on_its_explicit_trigger():
    text = HOST.read_text()
    assert "default: none" in text and "options: [none, freeze-sources, dry-run, execute]" in text
    gates = {"rp1-c1-freeze-sources": "inputs.rp1_c1_action == 'freeze-sources'", "rp1-c1-dry-run": "inputs.rp1_c1_action == 'dry-run'",
             "rp1-c1-execute": "inputs.rp1_c1_action == 'execute'"}
    for name, gate in gates.items():
        block = job_block(text, name)
        assert "github.event_name == 'workflow_dispatch' && " + gate in block
    probe = job_block(text, "rp1-c1-source-probe")
    assert "github.event_name == 'pull_request'" in probe and "github.head_ref == 'research/rp1-c1-wp4d-execution-readiness'" in probe
    assert "head.repo.full_name == github.repository" in probe


def test_secrets_and_permissions_are_scoped_and_no_input_reaches_a_shell():
    text = HOST.read_text()
    probe = job_block(text, "rp1-c1-source-probe")
    assert "permissions:\n      contents: read\n" in probe and "RP1_C1_SNAPSHOT_KEY" not in probe and "upload-artifact" in probe
    assert [u.strip() for u in re.findall(r"uses: actions/upload-artifact@v4\n(?:.*\n)*?\s+path: (.+)", probe)] == ["probe"]
    assert "RP1_C1_SNAPSHOT_KEY" not in text and "openssl" not in text
    for name in ("rp1-c1-freeze-sources", "rp1-c1-dry-run", "rp1-c1-execute"):
        assert "secrets.FRED_API_KEY" in job_block(text, name)
    freeze = job_block(text, "rp1-c1-freeze-sources")
    assert "upload-artifact" not in freeze and "secrets." not in freeze.replace("secrets.FRED_API_KEY", "")
    assert "github.event.pull_request.merged == true" in freeze and "github.event.pull_request.base.ref == 'main'" in freeze
    assert "github.head_ref == 'research/rp1-c1-hash-refetch-v2'" in freeze
    execute = job_block(text, "rp1-c1-execute")
    assert "contents: write" in execute and "pull-requests" not in execute and "GITHUB_RUN_ATTEMPT" in execute
    assert "group: rp1-c1-us-exposure-ladder-replication-v1-single-attempt" in execute
    for line in text.splitlines():
        if "${{ inputs." in line:
            assert re.match(r"\s+(if: |[A-Z0-9_]+: \$\{\{ inputs\.)", line), line   # inputs reach jobs only through `if:` or env
    for name in ("rp1-c1-freeze-sources", "rp1-c1-dry-run", "rp1-c1-execute"):
        block = job_block(text, name)
        for upload in re.findall(r"uses: actions/upload-artifact@v4\n(?:.*\n)*?\s+path: (.+)", block):
            assert upload.strip() in ("dry-run", "run")


def test_the_acquirer_refuses_to_write_inside_the_repository():
    acquire = load_script("acquire_rp1", "scripts/acquire_rp1_c1_us_sources.py")
    with pytest.raises(SystemExit, match="outside the repository"):
        acquire.main(["--output", str(ROOT / "data" / "rp1-c1-us-exposure" / "sources")])
    assert not (ROOT / "data" / "rp1-c1-us-exposure").exists()


def test_every_new_source_has_a_rights_class_and_restricted_ones_are_never_committed():
    assert set(SRC.SOURCE_RIGHTS) == set(SRC.SOURCES)
    assert {SRC.SOURCE_RIGHTS[s]["class"] for s in ("YAHOO_GSPC", "FRED_SP500", "YAHOO_SPY")} == {"RESTRICTED_NO_REDISTRIBUTION"}
    tracked = subprocess.run(["git", "ls-files"], capture_output=True, text=True, cwd=ROOT).stdout.split()
    assert not [p for p in tracked if "rp1-c1" in p and ("raw_" in p or p.endswith("normalized.csv"))]


def test_the_committed_template_authorizes_nothing():
    committed = json.loads((ROOT / X.AUTHORIZATION_TEMPLATE_PATH).read_text())
    assert committed == X.authorization_template() and committed["authorizes"] == "NOTHING"
    assert not (ROOT / X.AUTHORIZATION_PATH).exists()


def test_the_spec_records_the_route_storage_and_rights_and_the_scientific_digest_is_unchanged():
    spec, _ = SP.load_spec(ROOT)
    assert spec["lifecycle"]["route"]["workflow"] == X.HOST_WORKFLOW and spec["lifecycle"]["storage"]["rule"] == SRC.STORAGE
    pin = spec["inputs"]["usSnapshot"]
    assert spec["inputs"]["usRights"] == SRC.SOURCE_RIGHTS and pin["status"] in ("NOT_FROZEN", "FROZEN")
    assert (pin["status"] == "FROZEN") == bool(SP.freeze_manifest_paths(ROOT))          # the freeze PR adds exactly the manifest the spec pins
    assert SP.scientific_digest(spec) == "ad454ebbf2d7f0834b9de8ac136ba7842855d49146dbf1b123e1538fdc615252"   # the #249 preregistration's digest


def test_the_registered_closures_are_not_sessions():
    assert SRC.calendar_closure_check(pd.DatetimeIndex([]))["closuresThatAreSessions"] == []
    rows = SRC.calendar_closure_check(pd.DatetimeIndex(["2001-09-11", "2001-09-17"]))
    assert rows["referenceRowsOnClosures"] == ["2001-09-11"]


def test_identity_is_strict_about_instrument_type_units_and_frequency():
    good = {"symbol": "^GSPC", "currency": "USD", "exchangeTimezoneName": "America/New_York", "instrumentType": "INDEX"}
    assert SRC.identity_ok("YAHOO_GSPC", good)
    assert not SRC.identity_ok("YAHOO_GSPC", {**good, "instrumentType": "ETF"})
    assert SRC.identity_ok("FRED_DTB3", {"id": "DTB3", "units": "Percent", "frequency": "Daily"})
    assert not SRC.identity_ok("FRED_DTB3", {"id": "DTB3", "units": "Billions of Dollars", "frequency": "Daily"})
    assert not SRC.identity_ok("FRED_SP500", {"id": "SP500", "units": "Index", "frequency": "Weekly"})


# =======================================================================================================================================
# Synthetic vendor bytes in the exact shapes the acquirer receives
# =======================================================================================================================================
OFFSET = -18000


def stamps(dates):
    return [int((pd.Timestamp(d) + pd.Timedelta(hours=14, minutes=30)).timestamp()) for d in dates]


def chart(symbol, kind, dates, close, adj=None, dividends=None):
    ts = stamps(dates)
    result = {"meta": {"symbol": symbol, "currency": "USD", "exchangeTimezoneName": "America/New_York", "instrumentType": kind, "gmtoffset": OFFSET},
              "timestamp": ts, "indicators": {"quote": [{"close": [float(x) for x in close]}]}}
    if adj is not None:
        result["indicators"]["adjclose"] = [{"adjclose": [float(x) for x in adj]}]
    if dividends:
        result["events"] = {"dividends": {str(t): {"date": t, "amount": a} for t, a in dividends}}
    return json.dumps({"chart": {"result": [result]}}).encode()


def fred(series_id, units, frequency, dates, values):
    series = json.dumps({"seriess": [{"id": series_id, "units": units, "frequency": frequency}]}).encode()
    obs = json.dumps({"observations": [{"date": str(pd.Timestamp(d).date()), "value": f"{v:.6f}"} for d, v in zip(dates, values)]}).encode()
    return {"series.json": series, "observations.json": obs}


def synthetic_raw(end="2026-10-02", seed=7):
    rng = np.random.default_rng(seed)
    sessions = U.market_sessions("US", "1990-01-02", end)
    gspc = 330.0 * np.exp(np.cumsum(0.0003 + 0.011 * rng.standard_normal(len(sessions))))
    spy_days = sessions[sessions >= pd.Timestamp("1993-01-29")]
    spy_close = 44.0 * np.exp(np.cumsum(0.0003 + 0.011 * rng.standard_normal(len(spy_days))))
    ex = [i for i, d in enumerate(spy_days) if d.month in (3, 6, 9, 12) and d.day >= 15 and (i == 0 or spy_days[i - 1].month != d.month or spy_days[i - 1].day < 15)]
    div = np.zeros(len(spy_days))
    div[ex] = 0.004 * spy_close[ex]
    tr = np.r_[1.0, (spy_close[1:] + div[1:]) / spy_close[:-1]]
    adj = np.cumprod(tr)
    adj = adj / adj[-1] * spy_close[-1]
    business = pd.date_range("1990-01-02", end, freq="B")
    sp_dates = sessions[sessions >= pd.Timestamp("2016-10-03")]
    sp_values = pd.Series(gspc, index=sessions).reindex(sp_dates).to_numpy()
    return {"YAHOO_GSPC": {"chart.json": chart("^GSPC", "INDEX", sessions, gspc)},
            "YAHOO_SPY": {"chart.json": chart("SPY", "ETF", spy_days, spy_close, adj, [(stamps([spy_days[i]])[0], float(div[i])) for i in ex])},
            "FRED_SP500": fred("SP500", "Index", "Daily, Close", sp_dates, sp_values),
            "FRED_DTB3": fred("DTB3", "Percent", "Daily", business, np.maximum(0.0, 3.0 + 2.0 * np.sin(np.arange(len(business)) / 700.0)))}


class FakeTransport:
    YAHOO_HOSTS = ("https://fake",)

    def __init__(self, raw):
        self.raw, self.urls = raw, []

    def get(self, url):
        import urllib.parse
        self.urls.append(url)
        symbol=urllib.parse.unquote(urllib.parse.urlparse(url).path.split("/")[-1])
        sid=next(k for k,v in SRC.SOURCES.items() if v["symbol"]==symbol)
        return 200,self.raw[sid]["chart.json"],None

    def fetch_fred(self, entry, key, today):
        return {"status": {"observations": 200}, "host": "fake", "error": None, "raw": self.raw[_sid(entry)]}

    def fetch_yahoo(self, entry, today):
        return {"status": {"chart": 200}, "host": "fake", "error": None, "raw": self.raw[_sid(entry)]}


def _sid(entry):
    return next(k for k, v in SRC.SOURCES.items() if v is entry)


def acquire_synthetic(out, raw=None):
    acquire = load_script("acquire_rp1_syn", "scripts/acquire_rp1_c1_us_sources.py")
    acquire.kr_transport = lambda: FakeTransport(raw or synthetic_raw())
    assert acquire.main(["--output", str(out)]) == 0
    return Path(out) / "analysis"


def mini_repo(tmp):
    """A throwaway copy of exactly the files the spec, the equivalence audit and the harness read."""
    spec = json.loads((ROOT / SP.SPEC_PATH).read_text())
    files = set(spec["dependencyHashes"]) | set(X.HARNESS_FILES) | {SP.SPEC_PATH, str(Path(SP.SPEC_PATH).with_suffix(".sha256")), SP.SCIENTIFIC_SIDECAR,
                                                                   E.RESULT_PATH, "research_specs/kr-market-risk-model-v1.sha256", SP.EQUIVALENCE_PATH}
    files |= {E.SNAPSHOT_DIR + "/" + sid + "/normalized.csv" for sid in E.SOURCES.values()}
    for rel in files:
        target = tmp / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / rel, target)
    return tmp


def write_spec(root):
    builder = load_script("build_rp1_c1_mini", "scripts/build_rp1_c1_us_exposure_spec.py")
    spec = builder.build(root)
    path = root / SP.SPEC_PATH
    path.write_text(json.dumps(spec, sort_keys=True, indent=2, ensure_ascii=False) + "\n")
    path.with_suffix(".sha256").write_text(SP.digest(json.loads(path.read_text())) + "\n")
    assert SP.scientific_digest(spec) == (root / SP.SCIENTIFIC_SIDECAR).read_text().strip()
    return spec


class FakeGitHub:
    def __init__(self, main_sha):
        self.refs, self.main_sha, self.calls = {}, main_sha, []

    def __call__(self, method, path, payload=None, env=None):
        self.calls.append((method, path))
        if method == "GET" and path == "/git/ref/heads/main":
            return 200, {"object": {"sha": self.main_sha}}
        if method == "GET" and path.startswith("/git/matching-refs/"):
            prefix = "refs/" + path[len("/git/matching-refs/"):]
            return 200, [{"ref": r} for r in self.refs if r.startswith(prefix)]
        if method == "POST" and path == "/git/refs":
            if payload["ref"] in self.refs:
                return 422, {}
            self.refs[payload["ref"]] = payload["sha"]
            return 201, {}
        if method == "GET" and path.startswith("/git/ref/"):
            ref = "refs/" + path[len("/git/ref/"):]
            return (200, {"object": {"sha": self.refs[ref]}}) if ref in self.refs else (404, {})
        raise AssertionError((method, path))


def fake_git(root, head="a" * 40):
    def git(args, cwd):
        if args[0] == "rev-parse":
            return (head + "\n").encode()
        if args[0] == "show":
            path = Path(root) / args[1][len("HEAD:"):]
            if not path.exists():
                raise subprocess.CalledProcessError(128, args)
            return path.read_bytes()
        raise AssertionError(args)
    return git


def env_for(owner="owner", sha="a" * 40):
    return {"GITHUB_ACTIONS": "true", "GITHUB_EVENT_NAME": "workflow_dispatch", "GITHUB_REF": "refs/heads/main", "GITHUB_RUN_ATTEMPT": "1",
            "GITHUB_ACTOR": owner, "GITHUB_REPOSITORY": owner + "/Investment", "GITHUB_SHA": sha, "GH_TOKEN": "x"}


@pytest.fixture(scope="module")
def frozen_world(tmp_path_factory):
    """Acquire synthetic bytes, canonicalize, gate them, freeze and pin their hashes in a mini repository. Returns the pieces the tests need."""
    base = tmp_path_factory.mktemp("rp1-wp4d")
    root = mini_repo(base / "repo")
    snapshot = acquire_synthetic(base / "snapshot")
    probe = X.probe(root, snapshot)
    manifest = X.freeze_manifest(root, snapshot, run_id="111", commit_sha="a" * 40)
    path = root / X.freeze_manifest_path("111")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    spec = write_spec(root)
    return {"root": root, "snapshot": snapshot, "probe": probe, "manifest": manifest, "spec": spec, "base": base}


def test_the_synthetic_live_bytes_pass_every_dates_only_gate(frozen_world):
    readiness = frozen_world["probe"]["readiness"]
    assert readiness["decision"] == SP.DECISION_READY, readiness["blockers"]
    assert readiness["snapshotIdentity"] == "UNPINNED" and readiness["counters"]["usValueReads"] == 0
    assert readiness["details"]["economicReading"]["status"] == "ECONOMIC_READING_READY"
    assert readiness["details"]["economicReading"]["corporateActions"]["dividendEvents"] > 100
    assert readiness["details"]["vendorCrossCheck"]["status"] == "CONSISTENT"
    assert frozen_world["probe"]["retained"] is False


def test_the_manifest_carries_hashes_and_dates_never_a_value(frozen_world):
    manifest = frozen_world["manifest"]
    text = json.dumps(manifest)
    assert manifest["storage"] == SRC.STORAGE and manifest["analysisFiles"] == R.fingerprints(frozen_world["snapshot"])
    leaked = {"close", "adjclose", "value", "timestamp", "indicators", "quote", "amount"} & set(_keys(manifest))
    assert not leaked, leaked
    assert '"observations": [' not in text and '"timestamp": [' not in text
    assert frozen_world["spec"]["inputs"]["usSnapshot"]["status"] == "FROZEN"


def test_new_fetch_metadata_is_not_an_analysis_input(frozen_world, tmp_path):
    raw = tmp_path / "candidate"
    shutil.copytree(frozen_world["snapshot"].parent, raw)
    path = raw / "audit.json"
    doc = json.loads(path.read_bytes())
    doc["acquiredOn"] = "2099-12-31"
    path.write_text(json.dumps(doc))
    assert SP.verify_us_snapshot(frozen_world["spec"], frozen_world["root"], raw / "analysis")


def test_refetch_round_trips_without_a_key_or_artifact(frozen_world, tmp_path):
    second = acquire_synthetic(tmp_path / "refetched")
    assert SP.verify_us_snapshot(frozen_world["spec"], frozen_world["root"], second)
    assert R.fingerprints(second) == frozen_world["manifest"]["analysisFiles"]


def test_live_diagnostic_distinguishes_metadata_from_vendor_values(frozen_world, tmp_path):
    raw = synthetic_raw()
    doc = json.loads(raw["YAHOO_SPY"]["chart.json"])
    doc["chart"]["result"][0]["meta"]["regularMarketTime"] = 1
    raw["YAHOO_SPY"]["chart.json"] = json.dumps(doc, indent=3, sort_keys=True).encode()
    second = acquire_synthetic(tmp_path / "metadata-only", raw)
    report = R.compare_acquisitions(frozen_world["snapshot"], second)
    assert report["status"] == "EXACT_BOUNDED_INPUT_MATCH" and not report["changedFiles"]
    assert report["spy"]["sameRequestHash"] and report["spy"]["sameHost"]
    assert report["spy"]["normalizationDeterministic"]
    assert report["spy"]["otherMetadataKeysChanged"] == ["regularMarketTime"]


def test_vendor_adjclose_drift_is_diagnosed_not_hidden(frozen_world, tmp_path):
    raw = synthetic_raw()
    doc = json.loads(raw["YAHOO_SPY"]["chart.json"])
    doc["chart"]["result"][0]["indicators"]["adjclose"][0]["adjclose"][100] += .00001
    raw["YAHOO_SPY"]["chart.json"] = json.dumps(doc).encode()
    second = acquire_synthetic(tmp_path / "adjclose-drift", raw)
    report = R.compare_acquisitions(frozen_world["snapshot"], second)
    assert report["status"] == "BLOCKED_HASH_MISMATCH"
    assert report["causeCodes"] == ["YAHOO_VENDOR_ADJCLOSE_VALUE_DRIFT"]
    assert report["changedFiles"] == ["YAHOO_SPY/normalized.csv", "YAHOO_SPY/raw_chart.json"]
    assert report["spy"]["fields"]["adjclose"]["changedCells"] == 1
    for field in ("close", "dates", "timestamp", "actions.dividends"):
        assert report["spy"]["fields"][field]["changedCells"] == 0
    assert report["spy"]["adjacentAdjustedInputRatioEquality"]["changedPairs"] == 2
    assert not report["spy"]["riskStateReferenceChanged"]
    assert report["spy"]["normalizationDeterministic"]
    assert report["sourceArtifacts"] == report["lockClaims"] == report["strategyOutcomes"] == 0
    assert str(doc["chart"]["result"][0]["indicators"]["adjclose"][0]["adjclose"][100]) not in json.dumps(report)


def test_even_a_uniform_adjustment_drift_remains_blocked(tmp_path):
    raw = synthetic_raw()
    doc = json.loads(raw["YAHOO_SPY"]["chart.json"])
    adj = doc["chart"]["result"][0]["indicators"]["adjclose"][0]
    adj["adjclose"] = list(range(1000, 1000 + len(adj["adjclose"])))
    raw["YAHOO_SPY"]["chart.json"] = json.dumps(doc).encode()
    first = acquire_synthetic(tmp_path / "first", raw)
    adj["adjclose"] = [2 * v for v in adj["adjclose"]]
    raw["YAHOO_SPY"]["chart.json"] = json.dumps(doc).encode()
    second = acquire_synthetic(tmp_path / "second", raw)
    report = R.compare_acquisitions(first, second)
    assert report["status"] == "BLOCKED_HASH_MISMATCH"
    assert report["spy"]["adjacentAdjustedInputRatioEquality"]["changedPairs"] == 0
    assert report["spy"]["fields"]["adjclose"]["changedCells"] > 1000


def test_a_freeze_is_refused_once_an_authorization_is_committed(frozen_world, tmp_path):
    root = frozen_world["root"]
    (root / X.AUTHORIZATION_PATH).parent.mkdir(parents=True, exist_ok=True)
    (root / X.AUTHORIZATION_PATH).write_text("{}")
    try:
        with pytest.raises(X.Refused, match="AN_AUTHORIZATION_IS_COMMITTED"):
            X.freeze_manifest(root, frozen_world["snapshot"], run_id="2", commit_sha="b")
    finally:
        (root / X.AUTHORIZATION_PATH).unlink()


def test_two_committed_manifests_refuse(frozen_world):
    root = frozen_world["root"]
    extra = root / X.freeze_manifest_path("222")
    extra.write_text(json.dumps(frozen_world["manifest"]))
    try:
        with pytest.raises(ValueError, match="MORE_THAN_ONE_SOURCE_FREEZE_MANIFEST"):
            SP.us_snapshot_pin(root)
    finally:
        extra.unlink()


@pytest.fixture(autouse=True)
def _no_authorization_survives_a_test(request):
    """An authorization written by one test must never leak into the next, whether or not the test passed."""
    yield
    if "frozen_world" in request.fixturenames:
        (request.getfixturevalue("frozen_world")["root"] / X.AUTHORIZATION_PATH).unlink(missing_ok=True)


def authorize_world(world, owner="owner", acknowledge=True, mutate=None):
    root = world["root"]
    draft = X.authorization_draft(root, owner)
    if acknowledge:
        draft["acknowledgments"] = {k: True for k in X.ACKNOWLEDGMENTS}
    if mutate:
        mutate(draft)
    path = root / X.AUTHORIZATION_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(draft, indent=2, sort_keys=True) + "\n")
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.mark.parametrize("change, code", [
    (lambda e, a: e.update(GITHUB_REF="refs/heads/topic"), "REQUIRES_THE_FIRST_ATTEMPT"),
    (lambda e, a: e.update(GITHUB_RUN_ATTEMPT="2"), "REQUIRES_THE_FIRST_ATTEMPT"),
    (lambda e, a: e.update(GITHUB_EVENT_NAME="pull_request"), "REQUIRES_THE_FIRST_ATTEMPT"),
    (lambda e, a: e.update(GITHUB_ACTOR="someone-else"), "OWNER_DISPATCH_REQUIRED"),
    (lambda e, a: a.update(sha="0" * 64), "OWNER_AUTHORIZATION_HASH_MISMATCH"),
])
def test_authorization_refusals_before_anything_is_spent(frozen_world, change, code):
    sha = authorize_world(frozen_world)
    env, auth = env_for(), {"sha": sha}
    change(env, auth)
    api = FakeGitHub("a" * 40)
    with pytest.raises(X.Refused, match=code):
        X.authorize(frozen_world["root"], env, auth["sha"], fake_git(frozen_world["root"]), api)
    assert not api.refs
    (frozen_world["root"] / X.AUTHORIZATION_PATH).unlink()


def test_an_unacknowledged_or_stale_authorization_refuses(frozen_world):
    root = frozen_world["root"]
    for kwargs, code in (({"acknowledge": False}, "OWNER_SCOPE_OR_ACKNOWLEDGMENT_MISSING"),
                         ({"mutate": lambda d: d["pins"]["harness"].update({X.HOST_WORKFLOW: "0" * 64})}, "AUTHORIZED_PINS_DIFFER"),
                         ({"mutate": lambda d: d.update(authorizes="NOTHING")}, "OWNER_SCOPE_OR_ACKNOWLEDGMENT_MISSING")):
        sha = authorize_world(frozen_world, **kwargs)
        with pytest.raises(X.Refused, match=code):
            X.authorize(root, env_for(), sha, fake_git(root), FakeGitHub("a" * 40))
        (root / X.AUTHORIZATION_PATH).unlink()


def test_a_dispatched_commit_behind_main_or_an_existing_lock_refuses(frozen_world):
    root = frozen_world["root"]
    sha = authorize_world(frozen_world)
    with pytest.raises(X.Refused, match="DISPATCHED_COMMIT_IS_NOT_THE_MAIN_TIP"):
        X.authorize(root, env_for(), sha, fake_git(root), FakeGitHub("b" * 40))
    api = FakeGitHub("a" * 40)
    api.refs[X.LOCK_PREFIX + "-someotherspec"] = "c" * 40
    with pytest.raises(X.Refused, match="EXECUTION_LOCK_ALREADY_EXISTS"):
        X.authorize(root, env_for(), sha, fake_git(root), api)
    (root / X.AUTHORIZATION_PATH).unlink()


def test_values_cannot_be_read_without_permit_and_lock(frozen_world):
    with pytest.raises(ValueError, match="US_OUTCOME_ACCESS_WITHOUT_PERMIT"):
        X.load_values(frozen_world["root"], frozen_world["snapshot"], X.Counters(), None, None, "x")


def test_the_formal_execution_end_to_end_then_refuses_a_second_attempt(frozen_world, tmp_path):
    root = frozen_world["root"]
    snapshot = acquire_synthetic(tmp_path / "refetched")
    sha = authorize_world(frozen_world)
    api, order = FakeGitHub("a" * 40), []
    real_load = X.load_values

    def spy_load(*args, **kwargs):
        order.append(("values", sorted(api.refs)))
        return real_load(*args, **kwargs)
    X.load_values = spy_load
    try:
        manifest = X.execute(tmp_path / "run", root, snapshot, env_for(), sha, api, fake_git(root))
    finally:
        X.load_values = real_load
    spec_sha = (root / SP.SPEC_PATH).with_suffix(".sha256").read_text().strip()
    assert order == [("values", sorted([X.LOCK_PREFIX, X.lock_ref(spec_sha)]))]          # both lock refs exist before the first value read
    marker = json.loads((tmp_path / "run" / X.MARKER_FILE).read_text())
    assert marker["usValueReadsBeforeThisMarker"] == 0 and marker["lockRef"] == X.lock_ref(spec_sha)
    result = json.loads((tmp_path / "run" / X.RESULT_FILE).read_text())
    validation = json.loads((tmp_path / "run" / X.VALIDATION_FILE).read_text())
    assert validation["status"] == "CONSISTENT" and validation["checks"] > 200 and result["validationStatus"] == "CONSISTENT"
    assert set(result["candidates"]) == set(K.CANDIDATE_ORDER) and result["economicReadingStatus"] == "ECONOMIC_READING_READY"
    assert result["spyBasisDiagnostic"]["maxAbsoluteDailyDifference"] < 1e-9 and result["spyBasisDiagnostic"]["exDividendSessions"] > 100
    assert result["interpretation"]["reading"] in {"REPLICATED_CONTROL_RETAINED", "NOT_REPLICATED_US_NOMINATION", "NOT_REPLICATED_US_TRADEOFF"}
    report = (tmp_path / "run" / X.REPORT_FILE).read_text()
    for name in (K.PASSIVE,) + K.CANDIDATE_ORDER:
        assert f"| {name} |" in report
    assert "CVaR" in report and "rebound missed" in report and "up-market cost" in report
    assert manifest["counters"]["lockClaims"] == 1 and manifest["counters"]["usValueReads"] == 1
    assert not any("close" in k.lower() or "nav" == k.lower() for k in _keys(result))      # aggregate statistics only
    with pytest.raises(X.Refused, match="EXECUTION_LOCK_ALREADY_EXISTS"):
        X.execute(tmp_path / "run2", root, snapshot, env_for(), sha, api, fake_git(root))
    assert json.loads((tmp_path / "run2" / "gates-blocked.json").read_text())["lockClaimed"] is False
    (root / X.AUTHORIZATION_PATH).unlink()


def _keys(value):
    if isinstance(value, dict):
        for k, v in value.items():
            yield str(k)
            yield from _keys(v)
    elif isinstance(value, list):
        for v in value:
            yield from _keys(v)


def test_a_failed_readiness_refuses_before_the_lock(frozen_world, tmp_path):
    root = frozen_world["root"]
    raw = tmp_path / "refetched"
    shutil.copytree(frozen_world["snapshot"].parent, raw)
    snapshot = raw / "analysis"
    first = sorted(snapshot.rglob("normalized.csv"))[0]
    first.write_bytes(first.read_bytes() + b"\n")          # one added byte: the snapshot no longer matches the frozen manifest
    sha = authorize_world(frozen_world)
    api = FakeGitHub("a" * 40)
    with pytest.raises(X.Refused, match="READINESS_NOT_READY"):
        X.execute(tmp_path / "run", root, snapshot, env_for(), sha, api, fake_git(root))
    assert not api.refs and not (tmp_path / "run" / X.MARKER_FILE).exists()
    (root / X.AUTHORIZATION_PATH).unlink()


def test_the_dry_run_reads_no_value_and_claims_no_lock(frozen_world, tmp_path, monkeypatch):
    seen = []
    monkeypatch.setattr(X, "load_values", lambda *a, **k: (_ for _ in ()).throw(AssertionError("REAL_VALUE_READ")))
    monkeypatch.setattr(X, "claim_lock", lambda *a, **k: (_ for _ in ()).throw(AssertionError("LOCK")))
    monkeypatch.setattr(X, "read_values", lambda *a, **k: (_ for _ in ()).throw(AssertionError("REAL_VALUE_READ")))

    def fake_pipeline(values, economic_ready, counters):
        seen.append(values["reference"].index.min())
        return {}, None, {"status": "CONSISTENT", "checks": 1}
    monkeypatch.setattr(X, "evaluate_and_validate", fake_pipeline)
    monkeypatch.setattr(X, "interpretation", lambda result: {"decisionStatus": "SYNTHETIC"})
    monkeypatch.setattr(X, "render_report", lambda *a, **k: "report")
    out = X.dry_run(tmp_path / "dry", frozen_world["root"], frozen_world["snapshot"])
    assert out["lockClaimed"] is False and out["usValueReads"] == 0 and out["readiness"]["decision"] == SP.DECISION_READY
    assert out["readiness"]["snapshotIdentity"] == "MATCHES_THE_FROZEN_MANIFEST" and out["equivalence"] == "EXACT"
    assert out["readyToExecute"] is False and out["authorization"]["status"] == "NOT_ISSUED"
    assert seen and seen[0] >= pd.Timestamp(U.GRID_START)          # the pipeline ran on the invented series only


# =======================================================================================================================================
# The validator and the report on a small synthetic world
# =======================================================================================================================================
def small_world():
    sessions = U.market_sessions("US", "1990-01-02", "1999-12-31")
    rng = np.random.default_rng(3)
    close = pd.Series(100 * np.exp(np.cumsum(0.0002 + 0.014 * rng.standard_normal(len(sessions)))), index=sessions)
    days = pd.date_range("1990-01-02", "1999-12-31", freq="B")
    t = np.arange(len(days))
    values = {"reference": close, "asset": close * np.exp(0.0001 * np.arange(len(close))),
              "spread": pd.Series(np.sin(t / 200.0) + 0.2 * rng.standard_normal(len(days)), index=days),
              "vix": pd.Series(np.abs(18 + 8 * np.sin(t / 80.0) + 3 * rng.standard_normal(len(days))), index=days),
              "cash": pd.Series(4.0 + np.sin(t / 300.0), index=days)}
    config = {**U.us_config(), "analysisEnd": "1999-12-31"}
    return values, config


def test_the_independent_replay_equals_the_sealed_engine():
    values, config = small_world()
    sessions = U.market_sessions("US", "1990-01-02", "1999-12-31")
    states = U.layer_states(values["reference"].reindex(sessions), values["spread"], values["vix"], sessions, "US")
    schedule = U.decision_schedule(sessions, config["evaluationStart"], config["analysisEnd"], "US")
    window = sessions[sessions >= schedule["executionDate"].iloc[0]]
    cash = U.cash_interval_returns(values["cash"], window)
    for cid in K.CANDIDATE_ORDER:
        t = K.candidate_targets(states, schedule, cid)["target"].tolist()
        a = V.replay(values["reference"].reindex(window), schedule, t, U.US_BUY_COST, U.US_SELL_COST)
        b = K.replay_path(values["reference"].reindex(window), schedule, t, buy_cost=U.US_BUY_COST, sell_cost=U.US_SELL_COST)
        np.testing.assert_allclose(a["nav"], b["nav"], rtol=1e-13, atol=0)
        c = V.replay(values["asset"].reindex(window), schedule, t, U.US_BUY_COST, U.US_SELL_COST, cash)
        d = U.replay_path_with_cash(values["asset"].reindex(window), schedule, t, cash, buy_cost=U.US_BUY_COST, sell_cost=U.US_SELL_COST)
        np.testing.assert_allclose(c["nav"], d["nav"], rtol=1e-13, atol=0)


def test_the_validator_agrees_and_catches_a_changed_published_number():
    values, config = small_world()
    result = U.evaluate(values, config)
    ok = V.validate(values, config, result)
    assert ok["status"] == "CONSISTENT" and ok["checks"] > 60, ok["mismatches"][:3]
    for path in (("candidates", "C1", "net", "maxDrawdown"), ("candidates", "C2", "diagnostics", "monthlyCvar", "cvar"),
                 ("economic", "candidates", "C0", "costDrag"), ("candidates", "C3", "diagnostics", "upDownMarketGap", "upMarketCostPerYear")):
        bad = copy.deepcopy(result)
        node = bad
        for key in path[:-1]:
            node = node[key]
        node[path[-1]] += 1e-6
        out = V.validate(values, config, bad)
        assert out["status"] == "INCONSISTENT" and out["mismatchCount"] == 1 and out["mismatches"][0]["quantity"].endswith(path[-1])


def test_the_report_names_every_strategy_and_the_frozen_reading():
    values, config = small_world()
    result = U.evaluate(values, config)
    validation = V.validate(values, config, result)
    meaning = X.interpretation(result)
    report = X.render_report(result, validation, meaning, stamp=X.SYNTHETIC_STAMP)
    assert X.SYNTHETIC_STAMP in report and meaning["reading"] in report
    for name in (K.PASSIVE,) + K.CANDIDATE_ORDER:
        assert report.count(f"| {name} |") >= 2
    K.assert_no_forbidden_keys(meaning)


def test_the_interpretation_table_is_applied_mechanically():
    axes = {K.PASSIVE: {"netAnnualizedReturn": 0.1, "maxDrawdown": -0.5, "reducedSessionShare": 0.0},
            **{c: {"netAnnualizedReturn": 0.08, "maxDrawdown": -0.3, "reducedSessionShare": 0.3} for c in K.CANDIDATE_ORDER}}
    base = {"passive": {"summary": {"maxDrawdown": -0.5}}, "candidates": {c: {"net": {"maxDrawdown": -0.3}} for c in K.CANDIDATE_ORDER}}
    for nomination, reading in ((K.NOMINATION_NONE, "REPLICATED_CONTROL_RETAINED"), (K.NOMINATION_TRADEOFF, "NOT_REPLICATED_US_TRADEOFF"),
                                ("C1", "NOT_REPLICATED_US_NOMINATION")):
        out = X.interpretation({**base, "decision": {"developmentNomination": nomination, "axes": axes}})
        assert out["reading"] == reading and out["noProtectionInUs"] is False
    worse = {**axes, K.CONTROL: {"netAnnualizedReturn": 0.05, "maxDrawdown": -0.6, "reducedSessionShare": 0.3}}
    worse.update({c: {"netAnnualizedReturn": 0.05, "maxDrawdown": -0.6, "reducedSessionShare": 0.3} for c in K.CANDIDATE_ORDER})
    out = X.interpretation({**base, "decision": {"developmentNomination": K.NOMINATION_NONE, "axes": worse}})
    assert out["noProtectionInUs"] is True


def test_the_spy_basis_diagnostic_reconciles_close_plus_dividend():
    raw = synthetic_raw(end="1996-12-31")["YAHOO_SPY"]["chart.json"]
    out = X.spy_basis_diagnostic(raw, "1993-02-08", "1996-12-31")
    assert out["sessions"] > 900 and out["maxAbsoluteDailyDifference"] < 1e-9 and out["exDividendSessions"] >= 15


@pytest.mark.parametrize("change", ["price", "rate", "adjusted", "dividend", "split", "identity"])
def test_any_bounded_value_or_action_revision_refuses_before_lock(frozen_world, tmp_path, change):
    raw = synthetic_raw()
    sid, file = ("FRED_DTB3", "observations.json") if change == "rate" else ("YAHOO_SPY", "chart.json")
    doc = json.loads(raw[sid][file])
    if change == "rate":
        doc["observations"][0]["value"] = "99.000001"
    else:
        data = doc["chart"]["result"][0]
        if change == "price": data["indicators"]["quote"][0]["close"][0] += .000001
        if change == "adjusted": data["indicators"]["adjclose"][0]["adjclose"][0] += .000001
        if change == "dividend": next(iter(data["events"]["dividends"].values()))["amount"] += .000001
        if change == "split": data["events"]["splits"] = {"synthetic": {"date": data["timestamp"][10], "numerator": 2, "denominator": 1, "splitRatio": "2:1"}}
        if change == "identity": data["meta"]["currency"] = "CAD"
    raw[sid][file] = json.dumps(doc).encode()
    snapshot = acquire_synthetic(tmp_path / "changed", raw)
    with pytest.raises(ValueError, match="US_ANALYSIS_INPUT_DIFFERS"):
        SP.verify_us_snapshot(frozen_world["spec"], frozen_world["root"], snapshot)
    sha = authorize_world(frozen_world)
    api = FakeGitHub("a" * 40)
    with pytest.raises(X.Refused, match="READINESS_NOT_READY"):
        X.execute(tmp_path / "blocked", frozen_world["root"], snapshot, env_for(), sha, api, fake_git(frozen_world["root"]))
    assert not api.refs
    assert json.loads((tmp_path / "blocked/gates-blocked.json").read_bytes())["counters"]["usValueReads"] == 0


def test_appended_or_changed_after_end_rows_and_metadata_do_not_change_inputs(frozen_world, tmp_path):
    raw = synthetic_raw()
    for sid in ("YAHOO_GSPC", "YAHOO_SPY"):
        doc = json.loads(raw[sid]["chart.json"])
        data = doc["chart"]["result"][0]
        data["meta"]["regularMarketTime"] = 9999999999
        for i, t in enumerate(data["timestamp"]):
            if R.local_day(t, OFFSET) > U.ANALYSIS_END:
                data["indicators"]["quote"][0]["close"][i] *= 100
                if sid == "YAHOO_SPY": data["indicators"]["adjclose"][0]["adjclose"][i] *= 200
        if sid == "YAHOO_SPY":
            t = stamps(["2026-10-01"])[0]
            data["events"]["dividends"][str(t)] = {"date": t, "amount": 123456.789}
        raw[sid]["chart.json"] = json.dumps(doc).encode()
    for sid in ("FRED_DTB3", "FRED_SP500"):
        doc = json.loads(raw[sid]["observations.json"])
        doc["realtime_start"] = "2099-01-01"
        doc["observations"].append({"date": "2026-10-05", "value": "99999.12345"})
        raw[sid]["observations.json"] = json.dumps(doc).encode()
    second = acquire_synthetic(tmp_path / "appended", raw)
    assert R.provenance(second) != frozen_world["manifest"]["rawFilesAuditOnly"]
    assert R.fingerprints(second) == frozen_world["manifest"]["analysisFiles"]
    assert SP.verify_us_snapshot(frozen_world["spec"], frozen_world["root"], second)
    # The actual series the unchanged engine receives are identical; no second
    # historical evaluation or simulation is needed to prove this invariance.
    left, right = X.read_values(frozen_world["root"], frozen_world["snapshot"]), X.read_values(frozen_world["root"], second)
    for name in left:
        pd.testing.assert_series_equal(left[name], right[name])


def test_decimal_context_has_no_rounding_or_global_float_rebase():
    assert R.number("1.2300") == R.number("1.23") == "1.23"
    assert R.number("100.00000000000000000001") != R.number("100")
    assert float(R.number("100.00000000000000000001")) == float(R.number("100"))


def test_access_denial_publishes_no_source_and_does_not_prepare_inputs(tmp_path, monkeypatch, capsys):
    acquire = load_script("acquire_denied_rp1", "scripts/acquire_rp1_c1_us_sources.py")
    class Denied:
        YAHOO_HOSTS = ("https://fake",)
        def get(self, *_): return 403,b"","PRIVATE_SOURCE_SENTINEL"
        def fetch_fred(self, *_): return {"status": 403, "host": "fake", "raw": {}, "error": "PRIVATE_SOURCE_SENTINEL"}
        fetch_yahoo = fetch_fred
    acquire.kr_transport = Denied
    monkeypatch.setattr(R, "prepare", lambda *_: pytest.fail("prepared denied data"))
    assert acquire.main(["--output", str(tmp_path / "denied")]) == 1
    assert "PRIVATE_SOURCE_SENTINEL" not in capsys.readouterr().out
    assert not (tmp_path / "denied/analysis").exists()


def test_no_authorization_reaches_no_input_or_outcome_reader(frozen_world, tmp_path, monkeypatch):
    monkeypatch.setattr(SP, "readiness_audit", lambda *_args, **_kwargs: pytest.fail("input read without authorization"))
    monkeypatch.setattr(X, "load_values", lambda *_args: pytest.fail("outcome read without authorization"))
    api = FakeGitHub("a" * 40)
    with pytest.raises(X.Refused, match="NO_COMMITTED_OWNER_AUTHORIZATION"):
        X.execute(tmp_path / "unapproved", frozen_world["root"], frozen_world["snapshot"], env_for(), "", api, fake_git(frozen_world["root"]))
    assert not api.refs and not (tmp_path / "unapproved" / X.MARKER_FILE).exists()


def test_workflow_checks_owner_before_fetch_and_never_uploads_sources():
    text = HOST.read_text()
    block = job_block(text, "rp1-c1-execute")
    assert block.index(' authorization-check ') < block.index('python scripts/acquire_rp1_c1_us_sources.py')
    assert "'closed'" not in block  # no PR merge can trigger the formal execute
    dry = job_block(text, "rp1-c1-dry-run")
    assert "github.event.pull_request.merged == true" in dry
    assert "github.event.pull_request.base.ref == 'main'" in dry
    assert "startsWith(github.head_ref, 'research/rp1-c1-us-source-freeze-')" in dry
    assert "permissions:\n      contents: read" in dry
    for name in ("rp1-c1-freeze-sources", "rp1-c1-source-probe", "rp1-c1-dry-run", "rp1-c1-execute"):
        block = job_block(text, name)
        assert not any(t in block for t in ("openssl", "secret set", "snapshot.tar", "secrets.RP1_C1"))


def test_yahoo_request_interval_is_frozen_not_the_current_clock():
    import urllib.parse
    acquire=load_script("fixed_request_rp1", "scripts/acquire_rp1_c1_us_sources.py")
    transport=FakeTransport(synthetic_raw(end="1994-01-01"))
    for _ in range(2): acquire.fetch_yahoo_fixed(SRC.SOURCES["YAHOO_GSPC"],transport)
    assert transport.urls[0]==transport.urls[1]
    query=urllib.parse.parse_qs(urllib.parse.urlparse(transport.urls[0]).query)
    assert int(query["period1"][0])==int(pd.Timestamp(U.GRID_START,tz="UTC").timestamp())
    assert int(query["period2"][0])==int(pd.Timestamp("2026-09-18",tz="UTC").timestamp())
