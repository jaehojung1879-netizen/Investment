"""Bounded provider adapters; standard transport only, no fallback/bypass.

The membership CSV is the existing repository universe source, pinned to a Git
commit and retained verbatim. It is secondary evidence, not official effective
membership. Yahoo uses the pinned provider and the existing unadjusted/actions
contract, without invoking the adjusted or total-return datafeed paths.
"""
from datetime import datetime, timedelta, timezone
import json
import re
import urllib.error
import urllib.request

from . import collector_outcomes as CO
from .us_daily_market_data import LIVE, PRICE_OPTIONS, MembershipResponse, PriceResponse, Refused

REPOSITORY = "datasets/s-and-p-500-companies"
SOURCE_PATH = "data/constituents.csv"


def now_utc():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _get(url, max_bytes=2*1024*1024):
    request = urllib.request.Request(url, headers={"User-Agent": "InvestmentResearchData/1.0",
                                                  "Accept": "application/vnd.github+json" if "api.github.com" in url else "text/csv"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            data = response.read(max_bytes+1)
            if len(data) > max_bytes:
                raise Refused("SOURCE_RESPONSE_TOO_LARGE", "Membership response exceeded bounded size", CO.SCHEMA_CHANGED)
            return data
    except urllib.error.HTTPError as exc:
        body = exc.read(1000).decode("utf-8", "replace")
        message = f"HTTP {exc.code}: {body}"
        raise Refused("MEMBERSHIP_HTTP_REFUSAL", message, CO.classify_refusal(message)) from None
    except urllib.error.URLError as exc:
        raise Refused("MEMBERSHIP_TRANSPORT_REFUSAL", str(exc.reason), CO.NETWORK_ERROR) from None


def current_sp500():
    """No historical clone, no short/static fallback, no inferred effective date."""
    url = f"https://api.github.com/repos/{REPOSITORY}/commits?path={SOURCE_PATH}&per_page=1"
    try:
        revisions = json.loads(_get(url))
        latest = revisions[0]
        sha, changed = latest["sha"], latest["commit"]["committer"]["date"]
        if not re.fullmatch(r"[a-f0-9]{40}", sha):
            raise ValueError("Invalid source commit")
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise Refused("MEMBERSHIP_SOURCE_SCHEMA", str(exc), CO.SCHEMA_CHANGED) from exc
    raw_url = f"https://raw.githubusercontent.com/{REPOSITORY}/{sha}/{SOURCE_PATH}"
    raw = _get(raw_url)
    return MembershipResponse(raw=raw, source=raw_url, source_identity=f"{REPOSITORY}@{sha}:{SOURCE_PATH}",
                              observed_at=now_utc(), source_last_changed_at=changed, source_kind=LIVE)


def yahoo_daily(ticker, start, through):
    """Only recent daily bars, same pinned Yahoo convention as datafeed.

    raise_errors retains provider refusal text instead of silently translating
    a transport refusal into a missing price. Metadata is read from the already
    acquired PriceHistory object; do not trigger another unbounded history call.
    """
    import yfinance as yf

    if yf.__version__ != "0.2.65":
        raise Refused("UNREGISTERED_PROVIDER_VERSION", "Version the collector before changing its provider", CO.SCHEMA_CHANGED)
    end = (datetime.fromisoformat(through).date()+timedelta(days=1)).isoformat()
    try:
        security = yf.Ticker(ticker)
        frame = security.history(start=start, end=end, **PRICE_OPTIONS, keepna=True,
                                 prepost=False, rounding=False, timeout=20, raise_errors=True)
        history = getattr(security, "_price_history", None)
        raw_metadata = getattr(history, "_history_metadata", {}) or {}
        fields = ("symbol", "currency", "exchangeTimezoneName", "instrumentType", "exchangeName")
        metadata = {k: raw_metadata.get(k) for k in fields}
        metadata["acquisitionOptions"] = dict(PRICE_OPTIONS)
        return PriceResponse(frame=frame, metadata=metadata, observed_at=now_utc())
    except Refused:
        raise
    except Exception as exc:  # Provider error text is evidence, not proof of delisting.
        message = f"{type(exc).__name__}: {exc}"
        raise Refused("YAHOO_PROVIDER_REFUSAL", message, CO.classify_refusal(message)) from exc
