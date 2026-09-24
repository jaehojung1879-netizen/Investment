import copy
import json

from pipeline.config import load_config
from pipeline import replay_inputs as RI


LEGACY_V16_HASH = "3f4663c1434bea4fa2a747c0c5629dbe9baac991e72fecd4ef28d20432649e95"


def test_semantically_identical_ecos_representations_have_same_fingerprint(tmp_path):
    raw = json.loads((RI.REPLAY_POLICY_BASELINES.parent.parent / "config.json").read_text())
    bare = copy.deepcopy(raw)
    normalized = copy.deepcopy(raw)
    bare["ecos"]["KR"]["KTB_3Y"] = "817Y002"
    normalized["ecos"]["KR"]["KTB_3Y"] = {"seriesId": "817Y002", "itemCode": None}
    left, right = tmp_path / "left.json", tmp_path / "right.json"
    left.write_text(json.dumps(bare), encoding="utf-8")
    right.write_text(json.dumps(normalized), encoding="utf-8")
    assert RI.replay_config_policy(load_config(left)[0]) == RI.replay_config_policy(load_config(right)[0])


def test_unrelated_ecos_configuration_does_not_invalidate_replay():
    cfg, _ = load_config()
    before = RI.replay_config_policy(cfg)
    cfg.ecos_regions["KR"]["futureOnly"] = {"seriesId": "X", "itemCode": "Y"}
    assert RI.replay_config_policy(cfg) == before


def test_genuine_replay_relevant_change_changes_fingerprint():
    cfg, _ = load_config()
    before = RI.replay_config_policy(cfg)
    cfg.historical_replay["frequency"] = "M"
    assert RI.replay_config_policy(cfg) != before


def test_replay_v16_legacy_policy_is_compatible_but_remains_byte_immutable(tmp_path):
    cfg, _ = load_config()
    legacy = {"start": "2013-01-01", "configSha256": LEGACY_V16_HASH}
    current = {"start": "2013-01-01", **RI.replay_config_policy(cfg)}
    ok, detail = RI.policies_compatible(
        legacy, current, replay_version="replay-v16",
        baseline_root=RI.REPLAY_POLICY_BASELINES)
    assert ok and detail["classification"] == "REPRESENTATION_ONLY_CHANGE"

    store = RI.InputStore(tmp_path, "replay-v16", "data-v1")
    first = store.commit({}, through="2026-09-01", policy=legacy)
    second = store.commit({}, through="2026-09-02", policy=current)
    assert second["policy"] == first["policy"] == legacy


def test_true_semantic_change_still_fails_legacy_bridge():
    cfg, _ = load_config()
    cfg.longterm["minNames"] += 1
    current = {"start": "2013-01-01", **RI.replay_config_policy(cfg)}
    ok, detail = RI.policies_compatible(
        {"start": "2013-01-01", "configSha256": LEGACY_V16_HASH}, current,
        replay_version="replay-v16", baseline_root=RI.REPLAY_POLICY_BASELINES)
    assert not ok
    assert detail["classification"] == "REPLAY_SEMANTIC_CHANGE"
