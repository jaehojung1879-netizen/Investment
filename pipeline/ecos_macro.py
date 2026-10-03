"""Read-only BOK ECOS adapter. Native per-series cycles; current revised history.

Source contract: https://ecos.bok.or.kr/api/ . StatisticSearch uses row
pagination BEFORE table/cycle/periods. Never log URLs, payload errors or
transport exceptions: ECOS embeds credentials in the request path.
Only explicit manual workflows may call this adapter live. This module
is not wired into production or a historical Alpha study.
"""
from __future__ import annotations

import json
import math
import re
import urllib.request

BASE = "https://ecos.bok.or.kr/api"
CYCLE_DAILY, CYCLE_MONTHLY, CYCLE_QUARTERLY, CYCLE_ANNUAL = "D", "M", "Q", "A"
PIT_STATUS_FOR_ALL_SERIES = "REVISED_HISTORY"


class AmbiguousSeries(ValueError):
    """Missing verified selectors, cycle or source identity; never guess."""


def build_url(*, api_key, stat_code, cycle, start, end, item_code=None,
              item_code_2=None, item_code_3=None, item_code_4=None, first=1, last=1000):
    segments = [BASE, "StatisticSearch", api_key, "json", "kr", str(first), str(last),
                stat_code, cycle, start, end]
    for item in (item_code, item_code_2, item_code_3, item_code_4):
        if item is None:
            break
        segments.append(str(item))
    return "/".join(segments)


def resolve_spec(name, spec, *, ecos_series):
    del ecos_series  # table uniqueness never establishes semantic identity
    if (not spec.get("seriesId") or not spec.get("itemCode")
            or spec.get("cycle") not in {"D", "M", "Q", "A"}
            or spec.get("sourceStatus") != "LIVE_VALIDATED_SOURCE"):
        raise AmbiguousSeries(f"{name}: verified native cycle and item selection required")
    return dict(spec)


def request(api_key, service, *parts):
    """No exception text, URL, arbitrary server message or raw response escapes."""
    url = "/".join([BASE, service, api_key, "json", "kr", *map(str, parts)])
    try:
        with urllib.request.urlopen(url, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception:
        return {}, "TRANSPORT_OR_DECODE_ERROR"
    return payload, None


def parse_service(payload, service):
    if not isinstance(payload, dict):
        return [], "INVALID_ENVELOPE"
    envelope = payload.get(service, {})
    result = envelope.get("RESULT", payload.get("RESULT", {})) if isinstance(envelope, dict) else {}
    if isinstance(result, dict) and result.get("CODE", "INFO-000") != "INFO-000":
        code = str(result.get("CODE", ""))
        return [], code if re.fullmatch(r"(?:ERROR|INFO)-\d{3}", code) else "API_ERROR"
    rows = envelope.get("row") if isinstance(envelope, dict) else None
    return (rows, None) if isinstance(rows, list) else ([], "NO_ROWS")


def parse_response(payload):
    return parse_service(payload, "StatisticSearch")


def row_to_observation(row):
    date, raw = row.get("TIME"), row.get("DATA_VALUE")
    if raw in (None, "", "-"):
        return date, None
    try:
        value = float(str(raw).replace(",", ""))
    except (ValueError, TypeError):
        return date, None
    return date, value if math.isfinite(value) else None


def period(date, cycle):
    compact = date.replace("-", "")[:8]
    if cycle == "Q":
        return compact[:4] + "Q" + str((int(compact[4:6]) - 1) // 3 + 1)
    return compact[:{"D": 8, "M": 6, "A": 4}[cycle]]


def fetch_macro(cfg, start, end):
    """Fetch verified native series, paginated, without a shared cycle override.

    Unverified configurations abstain. Frame attrs carry per-series errors,
    native cycles and REVISED_HISTORY; no publication/vintage is inferred.
    """
    import pandas as pd
    if not cfg.has_ecos or not cfg.ecos_series:
        return None
    columns, errors = {}, {}
    for name, spec in cfg.ecos_series.items():
        try:
            resolved = resolve_spec(name, spec, ecos_series=cfg.ecos_series)
        except AmbiguousSeries:
            errors[name] = "DATA_LINEAGE_UNRESOLVED"
            continue
        cycle = resolved["cycle"]
        observations = {}
        for first in range(1, 100001, 1000):
            selectors = [resolved.get(k) for k in ("itemCode", "itemCode2", "itemCode3", "itemCode4")]
            parts = [first, first+999, resolved["seriesId"], cycle, period(start, cycle), period(end, cycle)]
            parts.extend(item for item in selectors if item is not None)
            payload, error = request(cfg.ecos_api_key, "StatisticSearch", *parts)
            rows, error = ([], error) if error else parse_response(payload)
            if error:
                errors[name] = error
                break
            for row in rows:
                date, value = row_to_observation(row)
                if date and value is not None:
                    observations[date] = value
            total = payload["StatisticSearch"].get("list_total_count")
            if len(rows) < 1000 or (total is not None and first+999 >= int(total)):
                break
        else:
            errors[name] = "PAGINATION_LIMIT"
        if observations and name not in errors:
            columns[name] = observations
    if not columns:
        return None
    frame = pd.DataFrame(columns).sort_index()
    frame.attrs.update(vintageStatus=PIT_STATUS_FOR_ALL_SERIES, errors=errors,
                       nativeCycles={n: cfg.ecos_series[n]["cycle"] for n in columns})
    return frame
