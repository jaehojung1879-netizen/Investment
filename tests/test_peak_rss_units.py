"""ru_maxrss is kilobytes on Linux and bytes on macOS, and the first real run
logged "peak RSS 6949.93 GB" for a 6.79 GB process because both divisors were
one factor of 1024 short.

The point of printing the number is to see growth coming before it becomes an
OOM. A figure a thousand times too large cannot do that — it just reads as
broken, which is how it stays unread.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.audit_portfolio import _peak_gb  # noqa: E402


class _Usage:
    def __init__(self, value):
        self.ru_maxrss = value


def _peak_with(platform, ru_maxrss):
    with mock.patch("resource.getrusage", return_value=_Usage(ru_maxrss)), \
         mock.patch.object(sys, "platform", platform):
        return _peak_gb()


def test_linux_kilobytes_become_gigabytes():
    # The exact value the first replay-v5 run reported.
    assert _peak_with("linux", 7_116_728) == pytest.approx(6.787, abs=1e-3)


def test_macos_bytes_become_gigabytes():
    assert _peak_with("darwin", 7_116_728 * 1024) == pytest.approx(6.787, abs=1e-3)


def test_the_two_platforms_agree_on_the_same_process():
    linux = _peak_with("linux", 4 * 1024 * 1024)          # 4 GB in KB
    macos = _peak_with("darwin", 4 * 1024 * 1024 * 1024)  # 4 GB in bytes

    assert linux == pytest.approx(4.0) and macos == pytest.approx(4.0)


def test_a_runner_sized_process_is_a_believable_number():
    """16 GB is the runner. Anything printing four digits is a unit bug."""
    assert _peak_with("linux", 15 * 1024 * 1024) < 20
