"""What a response from SEC MEANS. Shared vocabulary, not a fetcher.

SEC answers a refusal with an HTML block page, and it does so under several
status codes — 403 most often, sometimes 200. A caller that reads the status,
or that assumes a 200 body is data, records a refusal as content. So the
question "was this served" is decided here, once, and every probe asks it the
same way rather than each carrying its own copy.

The second half is the content coding. SEC's access policy asks callers to
send `Accept-Encoding: gzip, deflate`; urllib does not decompress what comes
back, and reading compressed bytes as text turns a SERVED response into an
apparent refusal. That is a silent failure mode, so it lives beside the
classifier that would otherwise be misled by it.
"""
from __future__ import annotations

import gzip
import io
import zlib

# The phrases SEC's own refusal pages carry. Matched on the BODY, because the
# status code cannot tell a block page from data.
BLOCK_MARKERS = (
    "Undeclared Automated Tool",
    "Request Rate Threshold Exceeded",
    "Your Request Originates from",
    "automated tool",
)

SERVED = "SERVED"
BLOCKED = "BLOCKED"
ERROR = "ERROR"


def decode_body(raw: bytes, encoding: str | None) -> bytes:
    """Undo the content coding we asked for; return the bytes if we cannot."""
    if not raw:
        return raw
    coding = (encoding or "").lower()
    try:
        if "gzip" in coding:
            return gzip.GzipFile(fileobj=io.BytesIO(raw)).read()
        if "deflate" in coding:
            return zlib.decompress(raw, -zlib.MAX_WBITS)
    except Exception:
        # Report what came back rather than pretending it decoded.
        return raw
    return raw


def classify(status: int | None, body: bytes) -> tuple[str, str | None]:
    """SERVED, BLOCKED or ERROR, plus the marker that decided it."""
    text = body[:2000].decode("utf-8", "replace") if body else ""
    for marker in BLOCK_MARKERS:
        if marker.lower() in text.lower():
            return BLOCKED, marker
    if status is None:
        return ERROR, None
    if status != 200:
        return ERROR, None
    stripped = text.lstrip()
    if stripped.startswith("{") or stripped.startswith("["):
        return SERVED, None
    # A 200 that is neither JSON nor a known marker is still not data.
    return BLOCKED, "200 with a non-JSON body"
