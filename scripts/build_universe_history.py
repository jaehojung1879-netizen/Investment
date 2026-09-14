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

  KR — the KRX Open API's `sto/stk_bydd_trd` (유가증권 일별매매정보), collected
  by `collect_krx_universe_snapshots.py` and read here via `--krx-snapshots`.
  It serves a dated per-issue cross-section of every KOSPI issue that traded
  on a date, carrying `MKTCAP` — so the universe is rebuilt by the same rule
  `universe._kr_kospi` applies today, at the older date. Probes run #4
  measured it POINT_IN_TIME back to 2013-01-02: 77.42% overlap with today and
  210 issues departed. Without that flag the Korean half is still refused;
  `kr_membership_is_not_available` says why, and that refusal is what the two
  earlier Korean sources earned.

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

from pipeline import historical_store as HS  # noqa: E402
from pipeline import krx_universe as KU  # noqa: E402

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


# Regions whose point-in-time membership cannot be established from the free
# sources, and are therefore left UNDESCRIBED rather than guessed. `pit_data`
# reads a ticker with no row as membership-unknown, keeps it if it is in
# today's list, and counts it against `membershipCoveragePct` — so the gap is
# reported instead of filled.
UNRESOLVED_REGIONS = ("KR",)


def kr_membership_is_not_available() -> str:
    """Why the Korean half is not written, spelled out where it is skipped.

    An earlier version of this script wrote two kinds of KR row, and both
    claimed more than the data supports:

      * every name in `KRX-DELISTING` — but that is "was ever delisted from
        KRX", not "was a member of the investable KOSPI universe". A 1998
        KOSDAQ shell is not a former constituent of a book that holds ~119
        large names, and there is no free source that says which delisted
        names ever were.
      * today's listed names with `listed: None`, meaning no lower bound —
        which admits a name that entered the universe in 2020 into the 2013
        cross-section. That is a look-ahead, not a survivorship fix.

    Both rows read as KNOWN membership, so the file reported
    membershipCoveragePct 100% and survivorship risk LOW over a Korean
    cross-section it had invented. Nothing caught it because Yahoo serves
    almost none of those tickers (17 of 3,010 in the first real run) — the
    correctness was resting on a vendor's failure.

    So: no KR rows, unless `--krx-snapshots` supplies collected KRX
    cross-sections. The replay then reads Korea as membership-unknown, keeps
    today's names, and reports the hole. This message is what a build with no
    such shards still prints, because a source that has not been collected
    closes nothing.
    """
    return ("KR point-in-time index membership has no free source; "
            "KRX-DELISTING is every delisted KRX name, not former index "
            "members. Left undescribed so the gap is measured.")


def kr_snapshots(store: Path, size: int,
                 current_universe: list[str] | None) -> list[tuple[str, set[str]]]:
    """Dated Korean cross-sections from collected KRX shards, or [] if none.

    `collect_krx_universe_snapshots.py` writes what KRX served; the universe
    RULE is applied here, by `krx_universe.members_on_date`, so changing it is
    a rebuild of this file rather than a re-collection of a decade of dates.

    Returning [] when the store is absent or empty is what keeps the refusal
    below intact: no shards means no Korean rows, exactly as before.
    """
    rows: list[dict] = []
    for path in sorted(store.glob("krx-universe-*.jsonl.gz")):
        rows.extend(HS.read_jsonl(path))
    if not rows:
        return []
    return KU.snapshots_from_rows(rows, size, current_universe)


def configured_kr(config_path: Path) -> list[str]:
    """Today's Korean universe, for the half of the rule that protects it.

    Read from the same `config.json` the replay reads. An unreadable config
    yields [], which costs only the protective half of `members_on_date` — the
    market-cap ranking still runs — so a missing file degrades the result
    rather than inventing one.
    """
    try:
        raw = json.loads(config_path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return []
    universe = raw.get("universe") if isinstance(raw, dict) else None
    names = (universe or {}).get("KR") if isinstance(universe, dict) else None
    return [str(t) for t in names] if isinstance(names, list) else []


def configured_universe_size(config_path: Path, fallback: int = 120) -> int:
    """`universeSize` from config — the same cap `universe._kr_kospi` applies.

    The reconstruction is only the universe's own rule if it uses the
    universe's own number, so it is read rather than repeated here.
    """
    try:
        raw = json.loads(config_path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return fallback
    size = raw.get("universeSize") if isinstance(raw, dict) else None
    try:
        size = int(size)
    except (TypeError, ValueError):
        return fallback
    return size if size > 0 else fallback


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
    parser.add_argument("--krx-snapshots", default=None,
                        help="collect_krx_universe_snapshots.py가 쓴 샤드 디렉터리. "
                             "없으면 KR은 지금까지처럼 기술되지 않은 채 남는다.")
    parser.add_argument("--config", default=str(ROOT / "config.json"),
                        help="universeSize와 오늘의 KR 유니버스를 읽을 설정 파일")
    parser.add_argument("--kr-universe-size", type=int, default=None,
                        help="기본값: config의 universeSize (universe._kr_kospi와 같은 수)")
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

    described_regions: set[str] = {"US"} if not args.skip_us else set()
    if not args.skip_kr:
        config_path = Path(args.config)
        size = (args.kr_universe_size if args.kr_universe_size
                else configured_universe_size(config_path))
        snapshots = (kr_snapshots(Path(args.krx_snapshots), size,
                                  configured_kr(config_path))
                     if args.krx_snapshots else [])
        if not snapshots:
            # Unchanged behaviour, and the reason is unchanged too: with no
            # dated source the only Korean rows available are ones that claim
            # more than the data supports.
            print(f"  KR: skipped — {kr_membership_is_not_available()}")
        else:
            kr = memberships_from_snapshots(snapshots, "KR")
            alive = sum(1 for row in kr.values() if row["delisted"] is None)
            print(f"  KR: {len(snapshots)} snapshots {snapshots[0][0]} .. "
                  f"{snapshots[-1][0]}; {len(kr)} names ever, {alive} current, "
                  f"{len(kr) - alive} left the universe (top {size} by market cap)")
            memberships.update(kr)
            described_regions.add("KR")

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

    # Deliberate prune, not a silent shrink: rows for a region this script no
    # longer claims to describe are removed, including ones an earlier version
    # wrote. The union above would otherwise preserve them forever, and they
    # are the fabricated membership this refuses to assert.
    # Only regions this build did NOT describe. A KR row written from collected
    # KRX cross-sections is the opposite of the fabricated membership this
    # prune exists to remove, and deleting it here would leave the collector
    # writing a decade of shards the file silently discards.
    unresolved = tuple(r for r in UNRESOLVED_REGIONS if r not in described_regions)
    invented = [t for t, row in merged.items()
                if row.get("region") in unresolved]
    for ticker in invented:
        del merged[ticker]
    if invented:
        print(f"  removed {len(invented)} rows for undescribable regions "
              f"{list(unresolved)}")

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(dict(sorted(merged.items())),
                              ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    by_region: dict[str, int] = {}
    for row in merged.values():
        by_region[row.get("region")] = by_region.get(row.get("region"), 0) + 1
    was = len(previous)
    print(f"wrote {out} — {len(merged)} names {by_region}"
          + (f" (was {was}, {len(merged) - was:+d})" if was else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
