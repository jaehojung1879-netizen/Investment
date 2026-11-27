"""One fixed-head, read-only bridge check; not a new strategy or count search."""
import csv
import gzip
import io
import json
from .adapters import HERE, GitSources
from .core import compare, verify_calendar

HEAD = "d3783d00ff8217d555160e898c02386e63219279"
BASE = "research/entry_state_role_etf_residual_v1/"
PINS = {
    BASE + "spec.json": "6b0254d7b7f08e0b7322b9e4531923f1c6593f64dde403f0e433931199d08751",
    BASE + "result.json": "a62babd0645f8e6b2c9d4bb03c82a247761afb9281dac8c88f4fda0e92607524",
    BASE + "nav-daily.csv.gz": "7eed201076321e5a2bdf9288763bacc18e8f450ddf60976721d55b0f06abb37d",
}


def main():
    source = GitSources(HERE.parents[1], {"blobs": {HEAD+":"+p: h for p, h in PINS.items()}})
    spec = source.json(HEAD, BASE + "spec.json")
    result = source.json(HEAD, BASE + "result.json")
    rows = list(csv.DictReader(io.StringIO(gzip.decompress(source.blob(HEAD, BASE + "nav-daily.csv.gz")).decode())))
    n = spec["spec"]["primaryNameCount"]
    candidate_id = f"KR:ENTRY_IN_RANK:N{n}:ETF"
    benchmark_id = "KR:ETF_ONLY:069500.KS"

    def adapt(sid):
        selected = [r for r in rows if r["strategyId"] == sid]
        if not selected:
            raise ValueError("DECLARED_PRIMARY_NAV_NOT_AVAILABLE_NO_ALTERNATIVE_SELECTED")
        r = selected[0]
        # Explicit source convention: initial state is already ETF; that control never trades.
        cost = "NET_ALREADY_CHARGED" if r["costBasis"] == "NO_TRADE_NO_COST" else r["costBasis"]
        return {"region": r["region"], "strategyId": sid, "studyId": result["studyId"],
                "currency": r["currency"], "frequency": r["frequency"], "returnBasis": r["returnBasis"],
                "costBasis": cost, "originalCostBasis": r["costBasis"],
                "evidenceClass": r["evidenceClass"], "sourceCommit": HEAD, "hashes": PINS,
                "dataSourceCommit": r["sourceCommit"], "producerCodeCommit": r["codeCommit"],
                "samplingMeaning": "COMPLETE_SOURCE_COMMON_KRX_NYSE_OBSERVATIONS_NOT_REGIONAL_DAILY",
                "nav": [[x["date"], float(x["nav"])] for x in selected]}

    candidate, benchmark = adapt(candidate_id), adapt(benchmark_id)
    regional = verify_calendar({**candidate, "calendarPolicy": "XKRX"}, [r[0] for r in candidate["nav"]])
    regional.pop("expectedDates")
    summary, _ = compare(candidate, benchmark, "2026-11-01")
    check = {"kind": "ONE_FIXED_HEAD_READ_ONLY_CONNECTION_NOT_A_STRATEGY_REPLAY", "pr": 304,
             "head": HEAD, "sourceHashes": PINS,
             "selection": "Producer's declared primary reference control only, NOT an optimal/permanent name count",
             "primaryNameCountInSource": n, "pair": [candidate_id, benchmark_id],
             "regionalCalendarDiagnostic": regional,
             "knownReferenceCalendarClosureNotProducerMissing": ["2026-05-25"],
             "originalReportedEtfCagrPct": result["regions"]["KR"]["etfOnly"]["cagrPct"],
             "originalReportedCandidateCagrPct": result["regions"]["KR"]["scenarios"][f"N{n}"]["ETF"]["ENTRY_IN_RANK"]["metrics"]["cagrPct"],
             "notes": ["#304 has real NAV, not just positions. Read through common envelopes; no stock count optimization.",
                       "Original CSV lacks studyId/hashes: attach them from pinned parent artifacts, do not infer from strategy labels.",
                       "NO_TRADE_NO_COST is retained as originalCostBasis and explicitly normalized to NET_ALREADY_CHARGED at ZERO trading cost, per the source's initial-ETF/no-trade convention. This is not investor total-return admission.",
                       "REPLAY_V16 forward-accumulated distributions are NOT A's phase-C corrected ETF basis. No series are spliced or benchmark corrected here.",
                       "A shared KRX/NYSE observation grid must not automatically be called 126/252 regional exchange sessions. Observed-point statistics use its original complete grid; regional H126/H252 remain UNAVAILABLE.",
                       "Raw XKRX4.11.1 lists2026-05-25 as open, a known closure already corrected in the pinned legacy source calendar. That one raw-reference mismatch is NOT called a producer missing-price defect."],
             "readout": summary}
    (HERE / "claude-connection.json").write_text(json.dumps(check, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"head": HEAD, "pair": check["pair"], "calendar": summary["pairedCalendar"],
                      "mddStatus": summary["dailyMdd"], "fullCagrGapPp": summary["scopes"]["FULL"]["cagrGapPp"]}))


if __name__ == "__main__":
    main()
