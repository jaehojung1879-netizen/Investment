"""One fixed, owner-authorized exploratory M3 evaluation; no strategy returns."""
import argparse
import datetime as dt
import hashlib
import gzip
import json
import math
import subprocess
from pathlib import Path

import numpy as np

from .geometry import known_before_month_end, month_end, origin_support, shift_month
from .parser import GROUPS, parse_table

ROOT = Path(__file__).resolve().parent


def parse_sources(source_dir):
    rows = json.loads(gzip.decompress((ROOT / "source-manifest.json.gz").read_bytes()))
    values, failures = {}, []
    for row in rows:
        ref = row.get("referenceMonth")
        if not ref or ref < "2003-07" or row["status"] != "METADATA_PRESENT":
            continue
        path = source_dir / (ref + ".pdf")
        if hashlib.sha256(path.read_bytes()).hexdigest() != row["sha256"]:
            raise ValueError("SOURCE_HASH_MISMATCH:" + ref)
        text = subprocess.check_output(["pdftotext", "-layout", str(path), "-"], timeout=30).decode()
        try:
            values[ref] = {"shipments": parse_table(text, 1), "unfilledOrders": parse_table(text, 3)}
        except ValueError as exc:
            failures.append({"referenceMonth": ref, "reason": str(exc), "sourceSHA256": row["sha256"]})
    return rows, values, failures


def build_examples(rows, values):
    metadata = {r["referenceMonth"]: r for r in rows if r.get("referenceMonth")}
    examples = []
    month = "2003-01"
    while month <= "2025-12":
        origin = origin_support(month, metadata)
        item = {**origin, "x": None, "baseline": None, "outcome": None}
        if origin["metadataSupport"]:
            past = origin["baselineFirstFullReferences"]
            future = origin["futureTargetReferences_METADATA_ONLY"]
            ref = origin["latestReferenceMonthKnownAtCutoff"]
            if all(m in values for m in past + future + [ref]):
                def growth(m, kind, group):
                    a, b = values[m][kind][group]
                    return math.log(a / b)
                item.update(
                    x=[growth(ref, "unfilledOrders", g) for g in GROUPS],
                    baseline=[sum(growth(m, "shipments", g) for m in past)/3 for g in GROUPS],
                    outcome=[sum(growth(m, "shipments", g) for m in future)/3 for g in GROUPS],
                )
        examples.append(item)
        month = shift_month(month, 1)
    return metadata, examples


def eligible_training(examples, cutoff, metadata):
    return [r for r in examples if r["cutoffMonth"] < cutoff and r["outcome"] is not None
            and all(known_before_month_end(metadata[m], month_end(cutoff))
                    for m in r["futureTargetReferences_METADATA_ONLY"])]


def metrics(baseline, candidate, outcome):
    b, c, y = map(np.asarray, (baseline, candidate, outcome))
    eb, ec = b-y, c-y
    mb, mc = float(np.mean(eb**2)), float(np.mean(ec**2))
    return {"baselineMAE": float(np.mean(abs(eb))), "candidateMAE": float(np.mean(abs(ec))),
            "baselineRMSE": math.sqrt(mb), "candidateRMSE": math.sqrt(mc),
            "pairedMSELossDifference": mb-mc, "skill": 1-mc/mb if mb > 0 else None}


def evaluate(rows, values):
    metadata, examples = build_examples(rows, values)
    forecasts = []
    for r in examples:
        cutoff = r["cutoffMonth"]
        if cutoff < "2009-01" or int(cutoff[5:]) not in (1, 4, 7, 10):
            continue
        train = eligible_training(examples, cutoff, metadata)
        out = {**r, "trainingMonthlyOrigins": len(train), "candidate": None, "beta": None}
        if r["outcome"] is None:
            out["excludedReason"] = "SOURCE_CHAIN_INCOMPLETE"
        elif len(train) < 60:
            out["excludedReason"] = "FEWER_THAN_60_COMPLETED_PAST_TRAINING_ORIGINS"
        else:
            x = np.asarray([a["x"] for a in train]).ravel()
            residual = (np.asarray([a["outcome"] for a in train])-np.asarray([a["baseline"] for a in train])).ravel()
            denom = float(x @ x)
            if not denom > 0:
                raise ValueError("ZERO_PREDICTOR_VARIATION_NO_ALTERNATIVE_MODEL")
            beta = float(x @ residual / denom)
            out.update(beta=beta, candidate=(np.asarray(r["baseline"])+beta*np.asarray(r["x"])).tolist(), excludedReason=None)
        forecasts.append(out)
    valid = [r for r in forecasts if r["candidate"] is not None]
    if len(forecasts) != 68 or len(valid) < 60:
        raise ValueError("FIXED_SUPPORT_GATE_FAILED")
    b,c,y = [np.asarray([r[k] for r in valid]) for k in ("baseline","candidate","outcome")]
    summary = metrics(b,c,y)
    # Resample four adjacent CALENDAR quarters, keeping missing slots and sectors together.
    loss = np.full((68,2), np.nan)
    for i,r in enumerate(forecasts):
        if r["candidate"] is not None:
            loss[i]=[np.mean((np.asarray(r[k])-r["outcome"])**2) for k in ("baseline","candidate")]
    rng=np.random.default_rng(20261101)
    samples=[]
    for _ in range(9999):
        starts=rng.integers(0,68,17)
        idx=((starts[:,None]+np.arange(4))%68).ravel()
        mb,mc=np.nanmean(loss[idx],axis=0)
        samples.append([mb-mc,1-mc/mb])
    intervals=np.quantile(samples,[.025,.975],axis=0)
    return {"study":"m3-backlog-to-shipments-3m-v1","classification":"OWNER_AUTHORIZED_EXPLORATORY_NOT_CONFIRMATORY",
            "fixedBlocks":68,"evaluatedBlocks":len(valid),"excludedBlocks":68-len(valid),
            "pairedIndustryCutoffRows":len(valid)*6,"effectiveTimeUnits":len(valid),
            "units":"natural-log monthly growth; target is three-month mean, NOT percent or real output",
            "metrics":summary,"calendarBlock95Interval":{"pairedMSELossDifference":intervals[:,0].tolist(),"skill":intervals[:,1].tolist()},
            "firstHalf":metrics(*[a[[r['cutoffMonth']<'2018-01' for r in valid]] for a in (b,c,y)]),
            "secondHalf":metrics(*[a[[r['cutoffMonth']>='2018-01' for r in valid]] for a in (b,c,y)]),
            "industries":{g:metrics(b[:,i],c[:,i],y[:,i]) for i,g in enumerate(GROUPS)},
            "forecasts":forecasts,
            "verdict":"IMPROVED_EXPLORATORY" if intervals[0,1]>0 else ("REJECTED" if intervals[1,1]<0 else "INCONCLUSIVE")}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--sources',type=Path,required=True)
    parser.add_argument('--execute-once',action='store_true')
    args=parser.parse_args()
    result_path=ROOT/'result.json'
    if result_path.exists():
        raise SystemExit('Existing result: no historical rerun')
    rows,values,failures=parse_sources(args.sources)
    audit={"parsedReleaseMonths":len(values),"failures":failures,"verdict":"NUMERIC_SOURCE_NO_GO" if failures else "NUMERIC_PARSER_PASS"}
    (ROOT/'numeric-audit.json').write_text(json.dumps(audit,indent=2)+'\n')
    if failures or not args.execute_once:
        print(json.dumps(audit));return
    lock=ROOT/'execution-started.json'
    with lock.open('x') as f:
        json.dump({"startedAtUtc":dt.datetime.now(dt.timezone.utc).isoformat(),"codeSHA256":hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},f)
    result=evaluate(rows,values)
    result_path.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='forecasts'},indent=2))


if __name__=='__main__':
    main()
