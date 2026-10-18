"""WP5 A0 input census. Default preview: no input or outcome access.

--verify-inputs checks the frozen WP1/WP2 bytes in an isolated preparation.
--inspect additionally requires those PRs merged, exact inputs on main and a
successful current-main Tests run before it opens any real observation input.
No option bypasses admission, trains, opens labels or writes a lock.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline import rp1_a0 as A  # noqa: E402
from scripts import rp1_us_universe as U  # noqa: E402
from pipeline import replay_inputs as RI  # noqa: E402
from pipeline import winner_inflection_execution as WI_CLOCK  # noqa: E402
from scripts import rp1_inspect_us_universe as S  # noqa: E402

WP1_SPEC = "docs/research-program/specs/rp1-inference-calibration-v1.json"
WP1_RESULT = "docs/research-program/results/rp1-inference-calibration-v1-result.json"
WP2_RESULT = "docs/research-program/results/rp1-wp2-us-universe-v1.json"
PINS = {WP1_SPEC: "c4270baa6314b1894b6996f1e80b53b9b27edd72eb5ae54f26f5ca8e5f6fbb5b",
        WP1_RESULT: "19a78059e7db002f30e9b7cd3935672a0f3d88a10d7be8a88f1f6d30aa4e8664",
        WP2_RESULT: "aaee82e7abff173333711d90163255a8e051d0243947b0327347522bb56b89b2"}


def contracts(root=ROOT):
    root = Path(root)
    for path, expected in PINS.items():
        if hashlib.sha256((root / path).read_bytes()).hexdigest() != expected:
            raise ValueError("PREDECESSOR_BYTES_CHANGED:" + path)
    spec = json.loads((root / S.SPEC).read_bytes())
    S.validate_spec(spec)
    wp1 = json.loads((root / WP1_RESULT).read_bytes())
    wp2 = json.loads((root / WP2_RESULT).read_bytes())
    if wp1["specSha256"] != PINS[WP1_SPEC] or wp1["result"]["studyABranch"]["US"] != "H252":
        raise ValueError("WP1_H252_NOT_CALIBRATED")
    if wp2["daily"]["selection"]["selectedRule"] != "R-b":
        raise ValueError("WP2_RULE_CHANGED")
    S.verify_historical_code(wp2, root)
    return spec, wp1, wp2


def api(path):
    return json.loads(subprocess.check_output(["gh", "api", "repos/jaehojung1879-netizen/Investment/" + path]))


def financial_available_at(public_day):
    # Calendar next day, then localize: adding 24 hours to an already localized
    # midnight would yield 23:00/01:00 across the US DST boundary.
    return (pd.Timestamp(public_day) + pd.Timedelta(days=1)).tz_localize("America/New_York").isoformat()


def main_admission(root=ROOT, github=api):
    blockers = []
    for number in (256, 257):
        pr = github(f"pulls/{number}")
        if not pr.get("merged"):
            blockers.append(f"PR_{number}_NOT_MERGED")
    sha = github("git/ref/heads/main")["object"]["sha"]
    runs = github("actions/workflows/tests.yml/runs?branch=main&per_page=20")["workflow_runs"]
    matching = [r for r in runs if r["head_sha"] == sha and r.get("event") == "push"]
    if not matching or matching[0].get("conclusion") != "success":
        blockers.append("CURRENT_MAIN_TESTS_NOT_SUCCESS")
    if not blockers:
        for path, expected in PINS.items():
            try:
                raw = subprocess.check_output(["git", "cat-file", "blob", sha + ":" + path], cwd=root,
                    env={**os.environ, "GIT_NO_LAZY_FETCH": "1"}, stderr=subprocess.DEVNULL)
            except subprocess.CalledProcessError:
                blockers.append("MAIN_INPUT_NOT_LOCALLY_AVAILABLE:" + path)
                continue
            if hashlib.sha256(raw).hexdigest() != expected:
                blockers.append("MAIN_PREDECESSOR_BYTES_CHANGED:" + path)
    return {"status": "ADMITTED" if not blockers else "BLOCKED_PRECONDITIONS", "mainSha": sha, "blockers": blockers}


def load_inputs(repo, spec):
    source = S.Sources(repo)
    manifest = json.loads(source.blob(S.S.SOURCE_COMMIT, S.S.MANIFEST))
    if manifest["sha256"] != S.S.MANIFEST_SHA or RI.digest({k: v for k, v in manifest.items() if k != "sha256"}) != S.S.MANIFEST_SHA:
        raise ValueError("REPLAY_MANIFEST_CHANGED")
    roles = ("price/20", "benchmark/20", "corporate-events/20")
    source.allowed_objects = {ref for name, refs in manifest["components"].items() if name.startswith(roles) for ref in refs}
    lineage = {}
    for role in ("price/source", "benchmark/source", "corporate-events/source"):
        refs = manifest["components"].get(role, [])
        if len(refs) != 1:
            raise ValueError("UNRESOLVED_SOURCE_LINEAGE:" + role)
        source.allowed_objects.update(refs)
        lineage[role] = source.component(refs[0])
    price_line = [r for r in lineage["price/source"] if r.get("region") == "US"]
    spy_line = [r for r in lineage["benchmark/source"] if r.get("region") == "US" and r.get("ticker") == "SPY"]
    if (len(price_line) != 1 or price_line[0].get("vendor") != "YAHOO_UNADJUSTED_WITH_ACTIONS" or
        price_line[0].get("distributions") != "YAHOO_ACTIONS" or len(spy_line) != 1 or
        spy_line[0].get("source") != "yahoo" or spy_line[0].get("symbol") != "SPY" or
        lineage["corporate-events/source"] != [{"adjustment": "as-traded-forward-total-return-v1", "anchor": "FIRST_OBSERVED_SESSION",
            "basis": "AS_TRADED_CLOSE_WITH_FORWARD_ACCUMULATED_TOTAL_RETURN", "vendor": "YAHOO_UNADJUSTED_WITH_ACTIONS"}]):
        raise ValueError("STOCK_SPY_ACTION_RECIPE_LINEAGE_MISMATCH")
    prices, frames, events = defaultdict(set), defaultdict(dict), defaultdict(list)
    for name, refs in sorted(manifest["components"].items()):
        if not name.startswith(roles):
            continue
        for ref in refs:
            rows = source.component(ref)
            if name.startswith("price/20"):
                U.presence(rows, manifest["through"], prices)
            for row in rows:
                t, d = row["ticker"], row["date"]
                if name.startswith("corporate-events/20"):
                    if t.endswith((".KS", ".KQ")) or d > "2025-12-31":
                        continue
                    if row.get("applied") is False:
                        raise ValueError("REFUSED_CORPORATE_ACTION_IN_SOURCE")
                    events[t].append((d, row.get("dividend", 0), row.get("split", 1)))
                    continue
                if (t == "SPY") != name.startswith("benchmark/20"):
                    continue  # SPY only from its pinned benchmark leg
                if t.endswith((".KS", ".KQ")) or d > "2025-12-31":
                    continue
                value = (row.get("Close"), row.get("Volume"))
                if d in frames[t] and frames[t][d] != value:
                    raise ValueError("CONFLICTING_PAST_PRICE_KEY")
                frames[t][d] = value
    frames = {t: pd.DataFrame.from_dict(rows, orient="index", columns=("Close", "Volume")).sort_index() for t, rows in frames.items()}
    for frame in frames.values():
        frame.index = pd.to_datetime(frame.index)
    members, sectors, evidence = source.json(S.S.MEMBERS)["snapshots"], source.json(S.S.SECTORS)["snapshots"], source.json(S.EVIDENCE)
    if evidence["pinnedMembershipSha256"] != source.receipts[S.S.CODE_BASE + ":" + S.S.MEMBERS]["sha256"]:
        raise ValueError("IDENTITY_EVIDENCE_FOR_DIFFERENT_MEMBERSHIP")
    filings = defaultdict(list)
    for year in range(2011, 2028):
        for row in source.rows(f"ledger/fundamentals/us/finnhub-{year}.jsonl.gz"):
            filings[row["ticker"]].append(row)
    calendar = S.S.RC.sessions("2011-01-01", "2026-01-10", "US")
    dates = [str(d.date()) for d in calendar.to_series().groupby(calendar.to_period("W")).max() if d.year in spec["years"]]
    return source, manifest, frames, prices, members, sectors, evidence, filings, calendar, dates, events


def observations(inputs, spec, wp2):
    source, manifest, frames, prices, members, sectors, evidence, filings, calendar, dates, events = inputs
    # Re-run only the WP2 census, never mutate its frozen measurement. Its
    # sample and eligibility-mask chains must match before any signal is built.
    check = U.measure(members, sectors, evidence, prices, [r for rows in filings.values() for r in rows], dates, spec,
                      through=manifest["through"])
    if check["sampleIdentity"] != wp2["weeklyCompatibility"]["sampleIdentity"]:
        raise ValueError("WP2_POPULATION_OR_HOLD_MASK_CHANGED")
    _, malformed, _, ambiguous = U.identity_maps(members, evidence, prices, manifest["through"])
    membership, industry = S.S.RAF.MembershipSnapshots(members), U.C.SectorBook(sectors)
    histories = {t: A.FilingHistory(t, rows) for t, rows in filings.items()}
    past = A.PastPrices(frames, calendar, events)
    provenance = S.S.W.Source(reference=S.S.SOURCE_COMMIT + ":" + S.S.MANIFEST, sha256=S.S.MANIFEST_SHA,
        vintage="PUBLIC_RECONSTRUCTION", observed_at=None, observation_gap="NOT_RETAINED")
    universe_source = S.S.W.Source(reference=S.S.CODE_BASE + ":" + S.S.MEMBERS,
        sha256=source.receipts[S.S.CODE_BASE + ":" + S.S.MEMBERS]["sha256"],
        vintage="COMMUNITY_GIT_OBSERVATIONS", observed_at=None, observation_gap="NOT_RETAINED")
    filing_receipts = {k: v for k, v in source.receipts.items() if "ledger/fundamentals/us/" in k}
    input_context = {"filingReceiptsSha256": RI.digest(filing_receipts), "priceManifestSha256": S.S.MANIFEST_SHA,
        "membershipSha256": universe_source.sha256,
        "sectorSha256": source.receipts[S.S.CODE_BASE + ":" + S.S.SECTORS]["sha256"]}
    out, details = [], {}
    for day in dates:
        snap = membership.on(day)
        rows = []
        for ticker in sorted(snap["members"]):
            sector, _ = industry.lookup(snap, ticker)
            normalized = malformed.get(ticker, ticker)
            reason = ("DEFINITIONALLY_EXCLUDED" if sector in ("Financials", "Real Estate") else
                "INDUSTRY_UNRESOLVED" if sector == U.C.UNCLASSIFIED else
                "KNOWN_IDENTITY_CONFLICT" if ticker in spec["knownSuspectSymbols"] or normalized in ambiguous or not U.ID.well_formed(normalized) else
                "NO_EXACT_SESSION_PRICE" if day not in prices.get(ticker, ()) else None)
            state = histories[ticker].at(day) if ticker in histories and reason is None else {"flag": None, "reason": "NO_VISIBLE_FILING", "deltas": {}, "fields": {}, "publicDay": None}
            pf = past.features(ticker, day) if reason is None else {"relative126": None, "size63": None}
            rows.append({"ticker": ticker, "sector": sector if sector != U.C.UNCLASSIFIED else None,
                "eligibilityReason": reason, "state": state, **pf,
                "deltaRoe": state["deltas"].get("roe"), "deltaOperatingMargin": state["deltas"].get("operatingMargin"),
                "deltaProfitMargin": state["deltas"].get("profitMargin"), "deltaEarningsGrowth": state["deltas"].get("earningsGrowth")})
        eligible = [r for r in rows if r["eligibilityReason"] is None]
        third = A.h3(eligible)
        composite = A.acceleration_controls(eligible)
        for row in rows:
            ticker, state = row["ticker"], row["state"]
            flags = {"A-H1": state["flag"], "A-H2": A.h2(state["flag"], row["relative126"]), "A-H3": third.get(ticker, (None, "INELIGIBLE"))[0]}
            raw = {"financial." + h.replace("-", "_"): float(v) if v is not None else None for h, v in flags.items()}
            raw.update({"financial.delta_operatingMargin": state["deltas"].get("operatingMargin"),
                "financial.earningsGrowth": state["fields"].get("earningsGrowth"), "financial.accelerationComposite": composite.get(ticker),
                "price.relative126": row["relative126"], "risk.size63": row["size63"]})
            # Exact detailed failure reasons travel alongside Cell's closed
            # missing vocabulary; no unknown is converted to zero.
            filing_context = {**input_context, "visibleSourceIds": state.get("sourceIds", [])}
            filing_source = S.S.W.Source(reference=S.S.SOURCE_COMMIT + ":A0-visible-derived-input-set:" + RI.digest(state.get("sourceIds", [])),
                sha256=RI.digest(filing_context), vintage="PUBLIC_RECONSTRUCTION", observed_at=None, observation_gap="NOT_RETAINED")
            financial_at = financial_available_at(state["publicDay"]) if state.get("publicDay") else None
            cells = tuple(S.S.W.Cell(name=k, value=v,
                unit="USD" if k == "risk.size63" else "binary" if k in ("financial.A_H1", "financial.A_H2", "financial.A_H3") else
                     "zscore" if k == "financial.accelerationComposite" else "ratio",
                available_at=(financial_at if k.startswith("financial.") and k not in ("financial.A_H2", "financial.A_H3", "financial.accelerationComposite")
                              else WI_CLOCK.close_at(day, final=False)) if v is not None else None,
                source=filing_source if k.startswith("financial.") else provenance,
                missing_reason=None if v is not None else "INCOMPLETE_CHAIN") for k, v in raw.items())
            key = S.S.W.Key("US", day, "replay-v16:US:" + ticker)
            details[key.sample_id] = {"A-H1": state["reason"],
                "A-H2": state["reason"] if state["flag"] is None else "PAST_126_SESSION_WINDOW_UNRESOLVED",
                "A-H3": third.get(ticker, (None, "INELIGIBLE"))[1]}
            issuer = U.cik(industry.cik(snap, ticker))
            out.append(S.S.W.Observation(key=key, ticker=ticker, issuer_id="CIK:" + issuer if issuer else None,
                identity_status="UNRESOLVED" if row["eligibilityReason"] == "KNOWN_IDENTITY_CONFLICT" else "PROVISIONAL",
                signal_at=WI_CLOCK.close_at(day, final=False), knowledge_policy="PUBLIC_RECONSTRUCTION", universe_source=universe_source,
                universe_available_at=snap["date"] + "T00:00:00Z", investable=row["eligibilityReason"] is None,
                eligibility_reason=row["eligibilityReason"], industry_id=row["sector"], industry_status="RECONSTRUCTED" if row["sector"] else "UNRESOLVED", cells=cells))
    return out, details


def inspect(repo, *, admission, root=ROOT):
    if admission["status"] != "ADMITTED":
        return {**admission, "sourceInputsOpened": 0, "formalA0Measurement": False}
    spec, wp1, wp2 = contracts(root)
    inputs = load_inputs(repo, spec)
    rows, details = observations(inputs, spec, wp2)
    report = A.measure(rows, missing_details=details)
    members = inputs[4]
    departed = {t for snapshot in members for t in snapshot["members"] if t not in members[-1]["members"]}
    report["populationAudit"] = A.population_audit(rows, departed)
    report.update(formalA0Measurement=True, mainAdmission=admission, predecessorPins=PINS,
        wp1Calibration=wp1["result"]["claims"]["US_H252"], sourceReceipts=inputs[0].receipts,
        wp2Mask=wp2["weeklyCompatibility"]["sampleIdentity"],
        codeHashes={p: hashlib.sha256((Path(root) / p).read_bytes()).hexdigest() for p in (
            "pipeline/rp1_a0.py", "scripts/rp1_inspect_a0.py", "pipeline/experiment_workbench.py",
            "pipeline/finnhub_derive.py", "pipeline/fundamental_acceleration.py", "pipeline/fundamental_acceleration_seal.py",
            "pipeline/us_multifactor_inputs.py")},
        rawInputPriceBasis="INHERITED_REPLAY_BASIS_NOT_WP0_VERIFIED")
    U.scan_output(report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--verify-inputs", action="store_true")
    group.add_argument("--inspect", action="store_true")
    parser.add_argument("--repo", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    if args.inspect:
        report = inspect(args.repo, admission=main_admission(args.repo))
    elif args.verify_inputs:
        spec, _, wp2 = contracts()
        report = {"status": "ISOLATED_PREPARATION", "formalA0Measurement": False, "sourceInputsOpened": 0,
            "predecessorPins": PINS, "populationMask": wp2["weeklyCompatibility"]["sampleIdentity"],
            "spec": {"id": spec["id"], "selectedRule": "R-b", "identityStatus": "PROVISIONAL"}}
    else:
        report = {"status": "PREVIEW_ONLY", "formalA0Measurement": False, "sourceInputsOpened": 0}
    print(json.dumps(report, sort_keys=True, ensure_ascii=False, allow_nan=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
