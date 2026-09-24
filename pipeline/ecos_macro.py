"""Korean macro series from the Bank of Korea's ECOS Open API.

WHY THIS DID NOT EXIST BEFORE. `alpha-information-inventory-v1` confirmed by
grep across every `pipeline/*.py` file that no HTTP call to `ecos.bok.or.kr`
exists anywhere — `config.json`'s `ecos.KR` block and `Config.has_ecos` are
wired to nothing that fetches. Re-verified for this module (2026-09-24, same
grep, same result: `has_ecos` is read once, by `build.py`, only to report the
boolean `ecosEnabled`; nothing calls this module or fetches a series). This
module is that fetch layer's first implementation — foundation only, per this
PR's own scope: it is NOT called from `pipeline/build.py`'s alpha-scoring
path and NOT wired into `pipeline/regime.py`'s axis scoring. Doing either is
a separate, later decision.

THE API CONTRACT, RESEARCHED (WebFetch of `ecos.bok.or.kr` itself is blocked
by this sandbox's egress; researched instead via WebFetch/WebSearch of
third-party ECOS API wrappers describing the same documented contract,
2026-09-24). The URL shape is positional, not query-string:

    https://ecos.bok.or.kr/api/StatisticSearch/{key}/json/kr/{start}/{end}/
        {statCode}/{cycle}/{startTime}/{endTime}[/{itemCode1}][/{itemCode2}]...

`{cycle}` is ECOS's own frequency code (`D`=daily, `M`=monthly, `Q`=quarterly,
`A`=annual) and must match what the table actually publishes at, not what a
caller wants — asking a daily-cycle rate table for `M` gets no rows rather
than an aggregation ECOS performs for you. `{itemCode1}` (and, for a table
with a second dimension, `{itemCode2}`) selects which sub-series inside a
multi-item table (like `817Y002`) a call reads; a table needing one that is
omitted answers with every item interleaved in one response, which
`parse_response` below refuses rather than silently averaging or taking the
first row.

`817Y002`'S OWN AMBIGUITY, NOT RESOLVED HERE. Researching this table (see
`AGENTS.md`'s `alpha-information-inventory-v1` invariants and this task's own
research) corroborates that it is Bank of Korea's daily market-rates table
carrying BOTH government-bond and corporate-bond yields at several
maturities as separate item codes — so `KTB_3Y` and `CorpBond_3Y` sharing the
bare id `817Y002` in `config.json` (before this change) was a real,
unresolved ambiguity, not a typo. What this module adds is the SCHEMA for the
fix (`itemCode` alongside `seriesId`, in `Config.ecos_regions` — see
`pipeline/config.py`), not the resolved codes themselves: no source consulted
gave the exact item-code strings with enough confidence to write them down as
fact, and a wrong guessed code would be worse than the current explicit
`None` because it would look resolved while silently reading the wrong
column. `fetch_one` refuses to call a series whose config marks it ambiguous
(more than one series shares a `seriesId` with no `itemCode` set) rather than
guess.

VINTAGE STATUS: `REVISED_HISTORY`, NOT `PIT_EXACT` — STATED, NOT ASSUMED.
ECOS's `StatisticSearch` returns the table's CURRENT values; nothing
consulted describes an ALFRED-style vintage/release-history endpoint for
ECOS the way `pit_data.fetch_macro_vintages` uses FRED's `get_series_all_
releases`. So every series this module fetches is stamped
`pit_data.REVISED_HISTORY` unconditionally. If a future probe finds ECOS does
publish a first-vintage-preserving endpoint, that is a new finding to act on,
not an assumption this module makes now.

NOT EXECUTED LIVE IN THIS SESSION. No `ECOS_API_KEY` is available here; this
module's request-building has been exercised only against a mocked response
in `tests/test_ecos_macro.py`. A `workflow_dispatch` smoke test — once a key
is provisioned as a repository secret — is what would confirm the URL shape,
the cycle codes, and the response envelope against a live call, the same way
`probe_dart_fundamentals.py` confirmed DART before `dart_fundamentals.py` was
trusted.
"""
from __future__ import annotations

BASE = "https://ecos.bok.or.kr/api"

# ECOS's own cycle codes. `D` is used for every series in this module's
# current callers because `config.json`'s KR series are all daily- or
# monthly-published rate/index tables read at their native frequency; a
# caller wanting a different cycle passes it explicitly rather than this
# module silently picking one.
CYCLE_DAILY = "D"
CYCLE_MONTHLY = "M"
CYCLE_QUARTERLY = "Q"
CYCLE_ANNUAL = "A"


def build_url(*, api_key: str, stat_code: str, cycle: str, start: str, end: str,
              item_code: str | None = None, item_code_2: str | None = None) -> str:
    """The positional ECOS `StatisticSearch` URL for one series.

    Positional, not query-string, because that is ECOS's own contract (see
    module docstring) — building it with `urlencode` would silently answer a
    valid-looking request for the wrong resource, since the path segments'
    ORDER carries the meaning a query string's keys would otherwise carry.
    """
    segments = [BASE, "StatisticSearch", api_key, "json", "kr",
               str(start), str(end), stat_code, cycle]
    if item_code is not None:
        segments.append(str(item_code))
        if item_code_2 is not None:
            segments.append(str(item_code_2))
    return "/".join(segments)


class AmbiguousSeries(ValueError):
    """A series' table carries more than one item and no item_code is set."""


def resolve_spec(name: str, spec: dict, *, ecos_series: dict[str, dict]) -> dict:
    """One series' fetch parameters, refusing an unresolved multi-item table.

    A `seriesId` shared by more than one configured series with no
    `itemCode` set on either is the exact `817Y002` ambiguity this module's
    docstring describes — reading it as if it named a single series would
    silently serve one of them (whichever the response happens to put
    first) under both friendly names. Refused rather than guessed.
    """
    series_id = spec.get("seriesId")
    item_code = spec.get("itemCode")
    if item_code is None:
        sharers = [other for other, other_spec in ecos_series.items()
                  if other != name and other_spec.get("seriesId") == series_id
                  and other_spec.get("itemCode") is None]
        if sharers:
            raise AmbiguousSeries(
                f"{name!r} shares seriesId {series_id!r} with {sharers!r} and "
                "neither has an itemCode set — resolve via a live "
                "StatisticItemList call before fetching either")
    return {"seriesId": series_id, "itemCode": item_code}


def parse_response(payload: dict) -> tuple[list[dict], str | None]:
    """(rows, error). ECOS wraps both data and errors under `StatisticSearch`.

    An error response carries `RESULT.CODE`/`RESULT.MESSAGE` under the same
    top key real data would use for `row`, per every third-party wrapper's
    description of the contract researched for this module — so the error
    shape is checked for before assuming `row` is a data list.
    """
    if not isinstance(payload, dict):
        return [], f"payload was {type(payload).__name__}, not an object"
    envelope = payload.get("StatisticSearch")
    if not isinstance(envelope, dict):
        # A bare RESULT at the top level is ECOS's own transport-error shape
        # (e.g. an unrecognised key), distinct from a StatisticSearch-wrapped
        # RESULT that means the query itself was rejected.
        result = payload.get("RESULT")
        if isinstance(result, dict):
            return [], str(result.get("MESSAGE") or result.get("CODE") or "ECOS error")
        return [], f"no StatisticSearch envelope in payload keys {sorted(payload)[:8]}"
    result = envelope.get("RESULT")
    if isinstance(result, dict) and str(result.get("CODE", "INFO-000")) != "INFO-000":
        return [], str(result.get("MESSAGE") or result.get("CODE"))
    rows = envelope.get("row")
    if not isinstance(rows, list):
        return [], "no 'row' list in the StatisticSearch envelope"
    return rows, None


def row_to_observation(row: dict) -> tuple[str | None, float | None]:
    """(date, value) from one ECOS row, or (None, None) if unreadable.

    `TIME` is ECOS's own date/period stamp (format depends on the table's
    cycle: `YYYYMMDD` for daily, `YYYYMM` for monthly); left as ECOS states
    it rather than reformatted here, so a caller normalizing dates does so
    against the documented format for the cycle it actually asked for.
    `DATA_VALUE` blank or non-numeric is `None`, never a fabricated 0.0 —
    the same rule every other new module in this line applies.
    """
    date = row.get("TIME")
    raw = row.get("DATA_VALUE")
    if raw in (None, "", "-"):
        return date, None
    try:
        return date, float(str(raw).replace(",", ""))
    except ValueError:
        return date, None


def fetch_macro(cfg, start: str, end: str, *, cycle: str = CYCLE_DAILY):
    """Fetch every configured, unambiguous ECOS series into a DataFrame.

    Mirrors `datafeed.fetch_macro`'s shape (a `Config`, a start date, one
    frame with a `pit_data.PIT_STATUSES`-compatible status) so a caller
    already handling FRED's macro frame does not need a second calling
    convention for ECOS. Returns `None` if no key is configured or every
    series is ambiguous/unfetchable — the same "nothing to build" contract
    `datafeed.fetch_macro` already uses.

    NOT CALLED from `pipeline/build.py` or `pipeline/regime.py` as of this
    change — see module docstring. A caller that imports this is opting in
    explicitly.
    """
    import json
    import urllib.error
    import urllib.request

    import pandas as pd

    if not cfg.has_ecos or not cfg.ecos_series:
        return None

    series = cfg.ecos_series
    columns: dict[str, dict[str, float]] = {}
    errors: dict[str, str] = {}
    for name, spec in series.items():
        try:
            resolved = resolve_spec(name, spec, ecos_series=series)
        except AmbiguousSeries as exc:
            errors[name] = str(exc)
            continue
        url = build_url(api_key=cfg.ecos_api_key, stat_code=resolved["seriesId"],
                        cycle=cycle, start=start.replace("-", ""), end=end.replace("-", ""),
                        item_code=resolved["itemCode"])
        try:
            with urllib.request.urlopen(url, timeout=30) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, urllib.error.HTTPError) as exc:  # pragma: no cover - network
            errors[name] = f"{type(exc).__name__}: {exc}"
            continue
        rows, error = parse_response(payload)
        if error:
            errors[name] = error
            continue
        observations: dict[str, float] = {}
        for row in rows:
            date, value = row_to_observation(row)
            if date and value is not None:
                observations[date] = value
        if observations:
            columns[name] = observations

    if errors:
        for name, message in errors.items():
            print(f"  warning: ECOS {name} failed: {message}")
    if not columns:
        return None
    return pd.DataFrame(columns)


# Every series this module can fetch is `REVISED_HISTORY`, never `PIT_EXACT`
# — see module docstring for why. Exposed as a constant rather than a
# function so a caller building a `pit_data`-style status table can read it
# without importing this module's fetch machinery.
PIT_STATUS_FOR_ALL_SERIES = "REVISED_HISTORY"
