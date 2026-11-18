"""Read-only checks of the committed experimental contract and saved evidence."""
from __future__ import annotations

import hashlib
import gzip
import json
import subprocess

import numpy as np
import pandas as pd

from research.kr_us_strategy_batch_v1 import common as C
from research.kr_us_strategy_batch_v1 import report as R

HERE, ROOT, OUT, REG = R.HERE, R.ROOT, R.OUT, R.REG


def load(path):
    def invalid(value):
        raise ValueError(f"nonfinite JSON constant: {value}")
    return json.loads(path.read_text(), parse_constant=invalid)


def policy_checks(market):
    checks = {}
    for path in sorted((OUT / market).glob("*fits*.json")):
        fits = load(path)
        for fit in fits:
            n, d = fit["nTrain"], pd.Timestamp(fit["fitDate"])
            if fit["maxTrainExit"] is not None:
                assert pd.Timestamp(fit["maxTrainExit"]) < d, path
            assert fit["sufficient"] == (n >= 104), path
            chosen = fit["chosen"]
            candidates = fit["candidateFits"]
            if chosen == "ETF":
                assert not any(c["eligible"] for c in candidates), path
            else:
                item = next(c for c in candidates if c["id"] == chosen)
                assert n >= 104 and item["riskGuard"] and item["lcb"] > 0 and item["eligible"], path
                assert item["meanCohortMdd"] >= item["etfMeanCohortMdd"], path
        checks[path.name] = {"annualFits": len(fits), "strictMaturity": True}
    return checks


def match_checks(market):
    path = OUT / market / "matching-audit.csv.gz"
    f = pd.read_csv(path)
    yes = f.loc[f.reason.eq("MATCHED")]
    assert yes.capRatio.between(.5 - 1e-12, 2 + 1e-12).all()
    assert np.allclose(yes.capRatio, yes.peerCap / yes.heldCap, rtol=1e-12, atol=1e-12)
    assert np.allclose(yes.logCapDistance, np.abs(np.log(yes.capRatio)), atol=1e-12)
    assert yes.peer.notna().all()
    for _, g in f.groupby(["date", "selector"]):
        peers = g.loc[g.reason.eq("MATCHED"), "peer"]
        assert peers.is_unique
        assert not set(peers) & set(g.ticker)
    return {"auditedLegs": len(f), "matchedLegs": len(yes),
            "capCaliperAndOneToOne": True, "excludeAllHeld": True}


def kr_checks(summary):
    result = {"policy": policy_checks("KR"), "matching": match_checks("KR")}
    max_error = 0.0
    for h in (126, 252):
        f = pd.read_csv(OUT / "KR" / f"cohorts-{h}.csv.gz", parse_dates=["date"]).set_index("date")
        keys = [k for k, v in REG["grid"].items() if v["market"] == "KR"]
        mask = f[[k + "_net" for k in keys]].notna().all(axis=1)
        for key in keys:
            s = summary["fixed"][str(h)][key]["common"]
            v = f[key + "_excess"]
            assert s["n"] == int((mask & v.notna()).sum())
            if s["mean"] is not None:
                assert abs(v[mask].mean() - s["mean"]) < 1e-10
        peer = pd.read_csv(OUT / "KR" / f"matched-{h}.csv").set_index("date")
        peer.index = pd.to_datetime(peer.index)
        for selector in REG["krSelectors"]:
            key = f"KR:{selector}:FIXED20:K5"
            err = (peer[selector + "_selection"] + peer[selector + "_replacement"] - f[key + "_excess"]).abs().max()
            if pd.notna(err):
                max_error = max(max_error, float(err))
        assert max_error < 1e-9
        at = pd.read_csv(OUT / "KR" / f"pername-cohort-{h}.csv.gz", parse_dates=["date"])
        sums = at.groupby(["id", "date"]).netContribution.sum()
        for key in at.id.unique():
            values = sums.loc[key]
            err = (values - f.loc[values.index, key + "_excess"]).abs().max()
            assert err < 1e-9, (key, h, err)
        result[str(h)] = {"originalDates": len(f), "matureWeeks": int(f.mature.sum()),
                          "portfolioCommonWeeks": int(mask.sum())}
    result["maxSelectionReplacementIdentityError"] = max_error
    with gzip.open(OUT / "KR/books.json.gz", "rt") as f:
        books = json.load(f)
    with gzip.open(OUT / "KR/matched-books.json.gz", "rt") as f:
        peers = json.load(f)
    for selector, by in peers.items():
        targets = books[f"KR:{selector}:FIXED20:K5"]
        for date, control in by.items():
            if control is None:
                continue
            target = targets[date]
            etf = "069500.KS"
            assert abs(sum(control.values()) - 1) < 1e-12
            assert control.get(etf, 0) == target.get(etf, 0)
            assert not ((set(control) - {etf}) & (set(target) - {etf}))
            assert sorted(w for t, w in control.items() if t != etf) == sorted(w for t, w in target.items() if t != etf)
    result["savedMatchedBooksPreserveEveryWeightAndETF"] = True
    return result


def us_checks(summary):
    result = {"policy": policy_checks("US"), "matching": match_checks("US")}
    b = pd.read_csv(OUT / "US" / "books.csv.gz")
    sums = b.groupby(["date", "config"]).weight.sum()
    assert np.allclose(sums, 1, atol=1e-12)
    assert b.weight.gt(0).all()
    for h in (126, 252):
        f = pd.read_csv(OUT / "US" / f"cohorts-excess-{h}.csv.gz", index_col=0)
        keys = [k for k, v in REG["grid"].items() if v["market"] == "US" and k in f]
        mask = f[keys].notna().all(axis=1)
        for key in keys:
            s = summary["fixed"][str(h)][key]["common"]
            assert s["n"] == int((mask & f[key].notna()).sum())
            if s["mean"] is not None:
                assert abs(s["mean"] - f.loc[mask, key].mean()) < 1e-10
        at = pd.read_csv(OUT / "US" / f"pername-cohort-{h}.csv.gz",
                         usecols=["date", "config", "netContribution"], parse_dates=["date"])
        sums = at.groupby(["date", "config"]).netContribution.sum().unstack("config")
        f.index = pd.to_datetime(f.index)
        expected = f.reindex(index=sums.index, columns=sums.columns)
        error = float((sums - expected).abs().max().max())
        assert error < 1e-10
        result[str(h)] = {"originalDates": len(f), "portfolioCommonWeeks": int(mask.sum())}
        result[str(h)]["maxDateNameContributionSumError"] = error
    return result


def nav_checks(market, summary):
    maximum = 0.0
    measured = 0
    for cadence, by in summary.get("ledgers", {}).items():
        wide = pd.read_csv(OUT / "KR" / f"nav-{cadence}.csv.gz", index_col=0, parse_dates=True) if market == "KR" else None
        for config, item in by.items():
            if "full" not in item:
                assert item.get("status") == "NOT_ESTIMABLE"
                continue
            if market == "KR":
                nav, benchmark = wide[config], wide["KR:ETF"]
            else:
                path = OUT / "US" / (f"NAV-{cadence}-" + config.replace(":", "_") + ".csv.gz")
                data = pd.read_csv(path, index_col=0, parse_dates=True)
                nav, benchmark = data.nav, data.spy
            recalculated = C.nav_window(nav, benchmark)
            for key in ("cagr", "etfCagr", "cagrGap", "mdd", "etfMdd", "annualArithmeticDailyGap", "compoundingRemainder"):
                err = abs(recalculated[key] - item["full"][key])
                maximum = max(maximum, err)
                assert err < 1e-9, (market, cadence, config, key, err)
            assert abs(item["full"]["cagrGap"] - item["full"]["annualArithmeticDailyGap"] - item["full"]["compoundingRemainder"]) < 1e-12
            measured += 1
    return {"measuredNavsRecalculated": measured, "maximumMetricErrorFromSavedNav": maximum,
            "cagrArithmeticCompoundingIdentity": True}


def main():
    contract = {}
    for name in ("DESIGN-ko.md", "registry.json"):
        original = subprocess.check_output(["git", "show", f"e6786ee:research/kr_us_strategy_batch_v1/{name}"], cwd=ROOT)
        assert original == (HERE / name).read_bytes(), name
        contract[name] = hashlib.sha256(original).hexdigest()
    for path, item in load(OUT / "artifact-manifest.json").items():
        assert hashlib.sha256((HERE / path).read_bytes()).hexdigest() == item["sha256"], path
    for path in OUT.rglob("*.json"):
        if "ledger-cache" not in path.parts:
            load(path)
    core, broad = (pd.read_csv(OUT / p) for p in ("core-comparisons.csv", "broad-etf-comparisons.csv"))
    for frame, n in ((core, 41), (broad, 115)):
        assert len(frame) == n * 2
        for _, g in frame.groupby("horizon"):
            assert len(g) == n and g.id.is_unique
            adj = C.holm(dict(zip(g.id, g.pUsedInFamily, strict=True)))
            assert np.allclose(g.pHolm, [adj[k] for k in g.id], atol=1e-12)
    prospective = load(OUT / "prospective-status.json")
    assert prospective["existingFilesByteUnchanged"]
    for path, sha in prospective["existingFilesSha256"].items():
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == sha
    result = {"designCommittedBeforeNewOutcomes": "e6786ee", "contractHashes": contract,
              "fixedCoreFamilySize": 41, "fixedBroadFamilySize": 115, "holmRecomputed": True,
              "artifactManifestVerified": True, "prospectiveFilesByteUnchanged": True, "markets": {}}
    if (OUT / "us-ctva-repair-receipt.json").exists():
        repair = load(OUT / "us-ctva-repair-receipt.json")
        assert repair["authorizationCommit"] == "4710738"
        assert repair["admissionOverrides"] == [] and repair["pricesReplaced"] is False
        assert repair["sourceSha256"] == "c8f9f48f042a7d9c9843ee7777c73d26852987880c9c30aad910966f99956fa5"
        result["ctvaInputRepairBeforeOutcomeInterpretation"] = "4710738"
    if (OUT / "us-source-bridge.json").exists():
        bridge = load(OUT / "us-source-bridge.json")
        assert bridge["changedTickers"] == ["CTVA"]
        assert max(abs(v["captureMinusPublished"]) for v in bridge["bridge"].values()) < 1e-12
        result["usOriginalBaselineRecoveredBeforeSourceRepair"] = True
    diagnostic = load(OUT / "matched-common-diagnostics.json")
    assert diagnostic["coreFamilyUnchanged"] == 41
    for by in diagnostic["markets"].values():
        for cell in by.values():
            assert cell["maxThreeTermIdentityError"] < 1e-9
    result["supplementIsPostHocDoesNotReplaceCore"] = True
    for market, fn in (("KR", kr_checks), ("US", us_checks)):
        path = OUT / market / "summary.json"
        if path.exists():
            s = load(path)
            result["markets"][market] = fn(s)
            result["markets"][market]["navs"] = nav_checks(market, s)
        else:
            result["markets"][market] = {"status": "INPUT_OR_RESULT_UNAVAILABLE"}
    R.dump(OUT / "verification.json", result)
    print(json.dumps(result, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
