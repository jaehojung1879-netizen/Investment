"""WID: preview (default), admit, request, synthetic, execute.

Only execute can open real prices; it requires reviewed admission, an exact
GitHub owner comment and a durable one-attempt claim. No collection or deploy.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import csv
import gzip
import io
import json
from pathlib import Path
import resource
import subprocess
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline import experiment_workbench as W  # noqa: E402
from pipeline import prospective_receipt_core as PRC  # noqa: E402
from pipeline import replay_inputs as RI  # noqa: E402
from pipeline import us_multifactor_inputs as MI  # noqa: E402
from pipeline import winner_inflection_admission as A  # noqa: E402
from pipeline import winner_inflection_execution as X  # noqa: E402
from pipeline import winner_inflection_filing_review as F  # noqa: E402
from scripts import inspect_experiment_sources as S  # noqa: E402


def load_permitted(root, spec, review, permit):
    """The ONE real-value entry point. Called only after durable authorization."""
    evidence = A.require_permit(permit)
    if evidence["specSha256"] != RI.digest(spec) or evidence["reviewSha256"] != RI.digest(review):
        raise ValueError("INPUT_SCOPE_CHANGED_AFTER_APPROVAL")
    X.validate_spec(spec)
    source = S.Sources(root)
    if spec["sourceCommit"] != S.SOURCE_COMMIT or spec["metadataCommit"] != S.CODE_BASE:
        raise ValueError("SOURCE_COMMIT_OUTSIDE_FIXED_REUSE_SCOPE")
    manifest = json.loads(source.blob(S.SOURCE_COMMIT, S.MANIFEST))
    if RI.digest({k: v for k, v in manifest.items() if k != "sha256"}) != spec["sourceManifestSha256"]:
        raise ValueError("SOURCE_MANIFEST_CHANGED")
    membership_document = source.json(S.MEMBERS)
    wanted = {t for snap in membership_document["snapshots"] if snap["date"] <= spec["signalEnd"] for t in snap["members"]} | {"SPY"}
    start, through = spec["sourceWindow"]["priceStart"], spec["sourceWindow"]["priceThrough"]
    roles = ("price/20", "benchmark/20", "corporate-events/20")
    selected_components = {name: refs for name, refs in manifest["components"].items()
                           if name.startswith(roles) and start[:7] <= name.split("/")[1] <= through[:7]}
    source.allowed_objects = {ref for refs in selected_components.values() for ref in refs}
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
            price_line[0].get("distributions") != "YAHOO_ACTIONS" or
            len(spy_line) != 1 or spy_line[0].get("source") != "yahoo" or spy_line[0].get("symbol") != "SPY" or
            lineage["corporate-events/source"] != [{"adjustment": "as-traded-forward-total-return-v1", "anchor": "FIRST_OBSERVED_SESSION",
                "basis": "AS_TRADED_CLOSE_WITH_FORWARD_ACCUMULATED_TOTAL_RETURN", "vendor": "YAHOO_UNADJUSTED_WITH_ACTIONS"}]):
        raise ValueError("STOCK_SPY_ACTION_RECIPE_LINEAGE_MISMATCH")
    quotes, volumes, events = defaultdict(dict), defaultdict(dict), defaultdict(list)
    for name, refs in sorted(selected_components.items()):
        for ref in refs:
            for row in source.component(ref):
                ticker, day = row["ticker"], row["date"]
                if ticker not in wanted or not start <= day <= through:
                    continue
                if name.startswith("corporate-events/"):
                    if row.get("applied") is False:
                        raise ValueError("REFUSED_CORPORATE_ACTION_IN_SOURCE")
                    events[ticker].append((day, row.get("dividend", 0), row.get("split", 1)))
                else:
                    value = row.get("Close")
                    if day in quotes[ticker] and quotes[ticker][day] != value:
                        raise ValueError("CONFLICTING_INPUT_PRICE")
                    quotes[ticker][day] = value
                    if "Volume" in row:
                        volumes[ticker][day] = row["Volume"]
    def frame(bucket):
        result = pd.DataFrame({t: pd.Series(v, dtype=float) for t, v in bucket.items()})
        result.index = pd.to_datetime(result.index)
        return result.sort_index()
    prices, volume = frame(quotes), frame(volumes)
    if "SPY" not in prices:
        raise ValueError("SPY_INPUT_MISSING")
    F.require_spy_action_history(events["SPY"], start, through)
    raw_columns = {}
    for ticker in prices:
        own = prices[ticker].dropna()
        raw_columns[ticker] = pd.Series(MI.as_traded_from_total_return(own.index, own.to_numpy(), events[ticker]), index=own.index)
    as_traded = pd.DataFrame(raw_columns)
    # Preserve the replay index as source evidence; labels and daily portfolio
    # economics both use the SAME reconstructed cash-reinvestment basis.
    vendor_prices, economic_columns, basis_problems = prices, {}, {}
    for ticker, native in raw_columns.items():
        try:
            usable = native if ticker == "SPY" else native.where(volume[ticker].reindex(native.index) > 0) if ticker in volume else native * np.nan
            economic_columns[ticker] = X.cash_reinvestment_close(usable, events[ticker])
        except ValueError as error:
            basis_problems[ticker] = str(error)
            economic_columns[ticker] = native * np.nan
    if "SPY" in basis_problems:
        raise ValueError("SPY_CASH_RETURN_BASIS_UNRESOLVED:" + basis_problems["SPY"])
    prices = pd.DataFrame(economic_columns)
    grouped = defaultdict(list)
    withheld = []
    for year in range(2011, spec["sourceWindow"]["lastFilingFiscalYear"] + 1):
        records = source.rows(f"ledger/fundamentals/us/finnhub-{year}.jsonl.gz")
        for row in records:
            grouped.setdefault(row["ticker"], [])  # preserve a wholly withheld issuer
        accepted, rejected = F.reviewed_filing_shard(records, year)
        withheld.extend(rejected)
        for row in accepted:
            grouped[row["ticker"]].append(row)
    identity = list(csv.DictReader(io.StringIO(gzip.decompress(source.local(S.US_IDENTITY)).decode())))
    if len({r["symbol"] for r in identity}) != len(identity):
        raise ValueError("DUPLICATE_SOURCE_IDENTITY_SYMBOL")
    membership = S.RAF.MembershipSnapshots(membership_document["snapshots"])
    industries = S.RAF.MembershipSnapshots(source.json(S.SECTORS)["snapshots"])
    terminal = {}
    if review.get("terminalSource"):
        desc = review["terminalSource"]
        path = Path(desc["path"]).resolve()
        if not path.is_relative_to("/workspace/wid-inputs") or path.suffix != ".json":
            raise ValueError("TERMINAL_SOURCE_OUTSIDE_APPROVED_INPUT_DIRECTORY")
        if A.file_sha(path) != desc["sha256"]:
            raise ValueError("TERMINAL_SOURCE_CHANGED")
        terminal = json.loads(path.read_bytes())
    source_evidence = W.Source("git:raw-input-bundle:" + S.SOURCE_COMMIT, RI.digest(source.receipts), S.SOURCE_COMMIT, None, "NOT_RETAINED")
    return F.prepare_inputs({"source": source_evidence, "asOf": evidence["authorizedAt"], "prices": prices, "volumes": volume, "asTraded": as_traded,
            "events": events, "filings": grouped, "withheldFilingMetadata": withheld,
            "identity": {r["symbol"]: r for r in identity},
            "membership": membership, "industries": industries, "terminal": terminal, "receipts": source.receipts, "lineage": lineage,
            "vendorPrices": vendor_prices, "basisProblems": basis_problems})


def save(root, layers):
    root = Path(root)
    for name, value in layers.items():
        A.append_record(root / name / "records.json", value)


def _main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", nargs="?", default="preview", choices=("preview", "admit", "request", "synthetic", "execute"))
    parser.add_argument("--spec", type=Path, default=ROOT / A.SPEC_PATH)
    parser.add_argument("--review", type=Path, default=ROOT / A.REVIEW_PATH)
    parser.add_argument("--run-root", type=Path, default=Path("/workspace/wid-executions/us-b-h126-2020-v1"))
    parser.add_argument("--request", type=Path)
    parser.add_argument("--approval-comment", type=int)
    args = parser.parse_args(argv)
    if args.mode == "execute":
        if not args.request or not args.approval_comment:
            parser.error("execute requires --request and --approval-comment; no implicit approval")
        document = json.loads(args.request.read_bytes())
        value = document.get("request", document)
        X.validate_spec(value["spec"])
        now = PRC.system_utc_now().isoformat()
        permit = A.authorize(value, ROOT, comment_id=args.approval_comment, now=now)
        run_root = Path(value["runRoot"])
        created_run = False
        try:
            run_root.mkdir(parents=True, exist_ok=False)
            created_run = True
            A.append_record(run_root / "attempt-started.json", {"permit": permit.evidence, "request": value})
            spec = value["spec"]
            resource.setrlimit(resource.RLIMIT_CPU, (spec["resourceBudget"]["cpuSeconds"],) * 2)
            resource.setrlimit(resource.RLIMIT_AS, (spec["resourceBudget"]["addressSpaceGiB"] * 1024 ** 3,) * 2)
            data = load_permitted(ROOT, spec, value["review"], permit)
            A.append_record(run_root / "source-receipts.json", data["receipts"])
            A.append_record(run_root / "withheld-filing-metadata.json", data["withheldFilingMetadata"])
            layers = F.execute(data, spec, checkpoint=lambda layer, key, value: A.append_record(run_root / layer / (key + ".json"), value))
            A.append_record(run_root / "attempt-completed.json", A.journal_record(value, status=layers["evaluation"]["status"],
                reason="fixed approved execution completed", result_informed=spec["resultInformed"]))
            print(json.dumps(layers["evaluation"], ensure_ascii=False, sort_keys=True, allow_nan=False))
            return 0 if layers["evaluation"]["status"] != "BLOCKED" else 2
        except Exception as error:
            failure = A.journal_record(value, status="FAILED", reason=type(error).__name__ + ":" + str(error), result_informed=value["spec"]["resultInformed"])
            if created_run and not (run_root / "attempt-failed.json").exists():
                A.append_record(run_root / "attempt-failed.json", failure)
            print(json.dumps({"status": "FAILED", "attemptConsumed": True, "reason": str(error)}))
            return 2
    spec = json.loads(args.spec.read_bytes())
    X.validate_spec(spec)
    review = json.loads(args.review.read_bytes())
    if args.mode in ("preview", "admit"):
        result = A.preflight(ROOT, spec, review)
        print(json.dumps({"specId": spec["id"], "mode": args.mode, **result}, ensure_ascii=False, sort_keys=True, indent=2))
        return 0 if args.mode == "preview" else 2 if result["status"] == "BLOCKED" else 0
    if args.mode == "request":
        prior = A.prior_attempts() if A.preflight(ROOT, spec, review)["status"] != "BLOCKED" else ()
        value = A.request(ROOT, spec, review, created_at=PRC.system_utc_now().isoformat(), run_root=args.run_root, prior_claims=prior)
        print(json.dumps({"request": value, "approvalText": "APPROVE WID_EXECUTION " + value["sha256"]
                          if value["admission"]["status"] != "BLOCKED" else None}, ensure_ascii=False, sort_keys=True, indent=2))
        return 0 if value["admission"]["status"] != "BLOCKED" else 2
    # Synthetic rehearsal never invokes source IO, GitHub or authorization.
    data, synthetic_spec = X.synthetic_fixture(spec)
    layers = F.execute(data, synthetic_spec)
    print(json.dumps({"evidenceClass": "SYNTHETIC_FIXTURE", **layers["evaluation"]}, ensure_ascii=False, sort_keys=True, allow_nan=False))
    return 0 if layers["evaluation"]["status"] != "BLOCKED" else 2


def main(argv=None):
    try:
        return _main(argv)
    except (ValueError, OSError, KeyError, TypeError, subprocess.CalledProcessError) as error:
        print(json.dumps({"status": "BLOCKED", "reason": str(error), "outcomeReads": 0, "modelFits": 0}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
