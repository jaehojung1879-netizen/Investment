"""Read saved NAVs only. No network, source collection, strategy fits or replay."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path

from .adapters import HERE, GitSources, discovery_pairs, weekly_pairs
from .core import compare


def guard_output(output, input_path=None):
    resolved = output.resolve()
    if not (resolved.is_relative_to(HERE) or resolved.is_relative_to(Path("/tmp"))):
        raise ValueError("OUTPUT_ONLY_IN_READOUT_DIRECTORY_OR_TMP_NO_SOURCE_LEDGER_WRITES")
    if resolved.suffix != ".json" or resolved.name in {"source-pins.json", "readout-plan.json"} or ".git" in resolved.parts:
        raise ValueError("DERIVED_JSON_OUTPUT_REQUIRED")
    if input_path and resolved == input_path.resolve():
        raise ValueError("INPUT_IS_READ_ONLY")
    detail = output.with_suffix(".windows.json.gz").resolve()
    if not (detail.is_relative_to(HERE) or detail.is_relative_to(Path("/tmp"))) or (input_path and detail == input_path.resolve()):
        raise ValueError("WINDOW_OUTPUT_MUST_NOT_OVERWRITE_SOURCE")


def run(pairs, as_of):
    summaries, windows = [], {}
    for identifier, c, b in pairs:
        result, detail = compare(c, b, as_of)
        summaries.append({"id": identifier, **result})
        windows[identifier] = detail
    return summaries, windows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, help="JSON {asOfDate, candidate, benchmark} using the documented NAV contract")
    parser.add_argument("--repo", type=Path, default=HERE.parents[1])
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    guard_output(args.out, args.input)
    if args.input:
        raw = args.input.read_bytes()
        obj = json.loads(raw)
        if obj["benchmark"].get("instrument") not in {"069500.KS", "SPY", "QQQ"}:
            raise ValueError("EXPLICIT_REGIONAL_ETF_INSTRUMENT_REQUIRED")
        if (obj["benchmark"]["region"] == "KR") != (obj["benchmark"]["instrument"] == "069500.KS"):
            raise ValueError("BENCHMARK_REGION_MISMATCH")
        pairs = [("CUSTOM", obj["candidate"], obj["benchmark"])]
        as_of = obj["asOfDate"]
        blocked, pins = [], {"inputSHA256": hashlib.sha256(raw).hexdigest()}
    else:
        pins = json.loads((HERE / "source-pins.json").read_text())
        import exchange_calendars as xc
        if xc.__version__ != pins["calendarPackageVersion"]:
            raise ValueError("PINNED_CALENDAR_PACKAGE_REQUIRED:" + pins["calendarPackageVersion"])
        source = GitSources(args.repo, pins)
        a = weekly_pairs(source)
        b, blocked = discovery_pairs(source)
        pairs, as_of = a + b, pins["readoutAsOfDate"]
    summaries, windows = run(pairs, as_of)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    detail_path = args.out.with_suffix(".windows.json.gz")
    encoded = json.dumps(windows, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    compressed = gzip.compress(encoded, mtime=0)
    detail_path.write_bytes(compressed)
    output = {"readout": "economic-path-readout-v1", "operation": "READ_EXISTING_NAV_ONLY_NOT_A_NEW_STRATEGY_BACKTEST",
              "asOfDate": as_of, "sourcePins": pins, "comparisons": summaries, "blockedComparisons": blocked,
              "QQQ": {"status": "PROVIDED_AS_SEPARATE_PAIR" if args.input and obj["benchmark"]["instrument"] == "QQQ" else "UNAVAILABLE",
                      "reason": "EXPLICIT_CUSTOM_QQQ_COMPARISON_SEPARATE_FROM_SPY" if args.input and obj["benchmark"]["instrument"] == "QQQ" else "QQQ_IS_SEPARATE_FROM_SPY; RETAINED_INPUTS_HAVE_NO_QQQ_NAV"},
              "windowDetails": {"file": detail_path.name, "sha256": hashlib.sha256(compressed).hexdigest()},
              "productionChanges": False, "strategyReexecution": False}
    args.out.write_text(json.dumps(output, indent=2, ensure_ascii=False, allow_nan=False) + "\n")
    print(json.dumps({"measuredComparisons": len(summaries), "blockedComparisons": len(blocked), "out": str(args.out)}))


if __name__ == "__main__":
    main()
