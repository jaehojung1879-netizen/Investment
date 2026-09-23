"""Export dated US constituent observations from a pinned upstream Git history."""
import argparse
import csv
import gzip
import io
import json
from pathlib import Path
import subprocess

REF = "3b2bb60e6269439cd75541eded6281c48e7681d1"
SOURCE = "https://github.com/datasets/s-and-p-500-companies"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_checkout", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    def git(*params):
        return subprocess.check_output(["git", "-C", str(args.source_checkout), *params], text=True)

    snapshots = []
    for line in git("log", "--reverse", "--format=%H %cI", REF, "--", "data/constituents.csv").splitlines():
        sha, stamp = line.split()
        rows = csv.DictReader(io.StringIO(git("show", sha + ":data/constituents.csv")))
        names = sorted({row["Symbol"].replace(".", "-") for row in rows if row.get("Symbol")})
        if len(names) >= 400:
            snapshots.append(dict(date=stamp[:10], members=names, sourceCommit=sha, publishedAt=stamp))
    value = dict(source=SOURCE, ref=REF, snapshots=snapshots)
    raw = (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(gzip.compress(raw, mtime=0))


if __name__ == "__main__":
    main()
