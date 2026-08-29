"""Reconstruct index membership by date, so the replay stops only seeing survivors.

WHY. The replay resolves its universe from TODAY's constituent lists and applies
them to 2013. Comparing the 2012-12-27 S&P 500 against the current one, 219 of
those 500 names — 44% — are absent today. They are not delisted penny stocks:
Alcoa, Anadarko, Aetna, Allergan. They left the index mostly by being acquired,
split, or shrinking out of it, and "shrinking out of it" correlates with poor
returns. Excluding them flatters every historical number the system publishes,
and `dataIntegrity.affectedObservationsPct` has been reporting 100% because of it.

WHERE THE DATA COMES FROM, AND WHAT IT COSTS. Nothing new is purchased.

  US — `datasets/s-and-p-500-companies` on GitHub is already the pipeline's
  constituent source. Its git history holds 194 dated revisions of
  `data/constituents.csv`, the oldest from 2012-12-27, which predates the replay
  start. Each commit is a point-in-time snapshot; walking them gives membership
  by date directly.

  KR — FinanceDataReader is already a dependency and exposes
  `StockListing('KRX-DELISTING')`: every delisted Korean name since 1960 with its
  delisting date, plus price history under `exchange='KRX-DELISTING'`.

WHAT THE DATES MEAN, INCLUDING WHERE THEY ARE WRONG.

  `listed` is the first snapshot a name appears in. That is at or after the real
  addition date, never before, so a name is never included earlier than it truly
  joined — the safe direction.

  `delisted` is the first snapshot a name is missing from. That is at or after
  the real removal, so a name can be held a little too long. Snapshot gaps reach
  seven months, so this side is the weaker one and is recorded rather than
  smoothed over. Leaving the index is not the same as ceasing to trade, so the
  error is bounded: the name still has prices, it just should not have been in
  the candidate pool.

  Names in the FIRST snapshot get `listed` = that snapshot's date. Most were
  members long before. Since the replay starts after it, they are all correctly
  present from the first replay date.

MEMBERSHIP IS NOT ENOUGH ON ITS OWN. `UniverseHistory.snapshot` drops any name
the price panel cannot serve, so a dead ticker without price history is still
missing from the cross-section. The replay must therefore also DOWNLOAD the
historical members, and the share it actually retrieves is what
`constituentCoveragePct` should report. This script writes the membership; it
does not pretend to have fixed coverage on its own.

Usage:
    python scripts/build_universe_history.py data/universe-history.json
        [--sp500-repo https://github.com/datasets/s-and-p-500-companies]
        [--skip-kr]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline.universe import _us_symbol  # noqa: E402

SP500_REPO = "https://github.com/datasets/s-and-p-500-companies"
SP500_PATH = "data/constituents.csv"


def _run(args: list[str], cwd: Path | None = None) -> str:
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True,
                          check=True, timeout=300).stdout


def sp500_snapshots(repo_url: str, workdir: Path) -> list[tuple[str, set[str]]]:
    """(date, members) for every dated revision of the constituents file."""
    clone = workdir / "sp500"
    print(f"cloning {repo_url} ...", flush=True)
    _run(["git", "clone", "--quiet", "--filter=blob:none", repo_url, str(clone)])
    log = _run(["git", "log", "--format=%H %ad", "--date=short", "--reverse",
                "--", SP500_PATH], cwd=clone)

    snapshots: list[tuple[str, set[str]]] = []
    for line in log.splitlines():
        sha, _, date = line.partition(" ")
        if not sha or not date:
            continue
        try:
            csv = _run(["git", "show", f"{sha}:{SP500_PATH}"], cwd=clone)
        except subprocess.CalledProcessError:
            continue
        members = set()
        for row in csv.splitlines()[1:]:
            symbol = row.split(",", 1)[0].strip().strip('"')
            if symbol:
                members.add(_us_symbol(symbol))
        # A snapshot far below index size means a malformed or partial commit,
        # and treating it as real would delist hundreds of names for a day.
        if len(members) >= 400:
            snapshots.append((date.strip(), members))
    return snapshots


def memberships_from_snapshots(snapshots: list[tuple[str, set[str]]],
                               region: str) -> dict[str, dict]:
    """First appearance -> listed; first absence after that -> delisted."""
    if not snapshots:
        return {}
    out: dict[str, dict] = {}
    for date, members in snapshots:
        for ticker in members:
            row = out.setdefault(ticker, {"listed": date, "delisted": None,
                                          "region": region})
            # A name that left and came back: clear the removal, keep the
            # original listing date so the earlier spell is not erased.
            row["delisted"] = None
        for ticker, row in out.items():
            if ticker not in members and row["delisted"] is None:
                row["delisted"] = date
    final = snapshots[-1][1]
    for ticker, row in out.items():
        if ticker in final:
            row["delisted"] = None
    return out


def kr_memberships(current: list[str]) -> dict[str, dict]:
    """Currently listed KOSPI names plus every delisted one FDR knows about."""
    out: dict[str, dict] = {}
    try:
        import FinanceDataReader as fdr
    except Exception as exc:                       # pragma: no cover - optional
        print(f"  warning: FinanceDataReader unavailable ({exc}); KR skipped")
        return out

    for ticker in current:
        out[ticker] = {"listed": None, "delisted": None, "region": "KR"}

    try:
        dead = fdr.StockListing("KRX-DELISTING")
    except Exception as exc:                       # pragma: no cover - network
        print(f"  warning: KRX-DELISTING listing failed ({exc}); "
              f"KR keeps survivors only")
        return out

    columns = {str(c).lower(): c for c in dead.columns}
    symbol_col = columns.get("symbol") or columns.get("code")
    date_col = next((columns[k] for k in ("delistingdate", "delisting_date", "date")
                     if k in columns), None)
    if not symbol_col or not date_col:
        print(f"  warning: unexpected KRX-DELISTING columns {list(dead.columns)}")
        return out

    added = 0
    for _, row in dead.iterrows():
        symbol = str(row[symbol_col]).strip()
        if not symbol or not symbol.isdigit():
            continue
        when = str(row[date_col])[:10]
        if not when or when == "nan":
            continue
        ticker = f"{symbol}.KS"
        if ticker in out:
            continue
        out[ticker] = {"listed": None, "delisted": when, "region": "KR"}
        added += 1
    print(f"  KR: {len(current)} listed + {added} delisted")
    return out


def read_existing(path: Path) -> dict[str, dict]:
    """Whatever membership is already recorded, or {} if there is none."""
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {}
    if not isinstance(raw, dict):
        return {}
    return {str(k): dict(v) for k, v in raw.items() if isinstance(v, dict)}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("out")
    parser.add_argument("--sp500-repo", default=SP500_REPO)
    parser.add_argument("--skip-kr", action="store_true")
    parser.add_argument("--skip-us", action="store_true")
    parser.add_argument("--rebuild", action="store_true",
                        help="overwrite instead of merging with the "
                             "existing file")
    args = parser.parse_args(argv)

    memberships: dict[str, dict] = {}
    with tempfile.TemporaryDirectory() as tmp:
        if not args.skip_us:
            snapshots = sp500_snapshots(args.sp500_repo, Path(tmp))
            if not snapshots:
                print("ERROR: no usable S&P 500 snapshots; refusing to write a "
                      "membership file that would silently be survivors-only.")
                return 1
            us = memberships_from_snapshots(snapshots, "US")
            alive = sum(1 for row in us.values() if row["delisted"] is None)
            print(f"  US: {len(snapshots)} snapshots {snapshots[0][0]} .. "
                  f"{snapshots[-1][0]}; {len(us)} names ever, {alive} current, "
                  f"{len(us) - alive} left the index")
            memberships.update(us)

    if not args.skip_kr:
        from pipeline.config import load_config
        from pipeline import universe as universe_mod
        cfg, _ = load_config()
        # The replay resolves KR dynamically (~119 names), not from the ~44 in
        # config. Building membership from the static list would leave the rest
        # with unknown membership and drag measured coverage down for no reason.
        try:
            resolved, _diag = universe_mod.resolve(cfg)
            current_kr = list(resolved.get("KR") or [])
        except Exception as exc:
            print(f"  warning: dynamic KR resolve failed ({exc}); using config list")
            current_kr = list(cfg.universe.get("KR") or [])
        memberships.update(kr_memberships(current_kr))

    out = Path(args.out)
    # Merged with what is already on disk, never overwritten. CI rebuilds this
    # file on every replay run, and the KR half comes from a live vendor call:
    # a day when FinanceDataReader returns a shorter list would otherwise erase
    # names from the historical cross-section, which changes what every past
    # rank meant while looking like a routine refresh.
    #
    # Membership history is monotone — a name that was ever in the index was
    # ever in the index — so a union is not a workaround for the failure, it is
    # the correct semantics. --rebuild is there for when the file itself is
    # believed wrong.
    previous = read_existing(out) if not args.rebuild else {}
    merged = dict(previous)
    merged.update(memberships)
    dropped = sorted(set(previous) - set(memberships))
    if dropped and not args.rebuild:
        print(f"  kept {len(dropped)} names this build did not return "
              f"(e.g. {dropped[:5]})")

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(dict(sorted(merged.items())),
                              ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    by_region: dict[str, int] = {}
    for row in merged.values():
        by_region[row.get("region")] = by_region.get(row.get("region"), 0) + 1
    was = len(previous)
    print(f"wrote {out} — {len(merged)} names {by_region}"
          + (f" (was {was}, +{len(merged) - was})" if was else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
