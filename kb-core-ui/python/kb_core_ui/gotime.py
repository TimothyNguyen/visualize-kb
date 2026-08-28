"""Just enough of Go's time.Time for the two things this port does with one:
derive an id from UnixNano and render RFC3339Nano, which is also how
encoding/json marshals a time.Time.
"""

from __future__ import annotations

import datetime
import re
import time
from dataclasses import dataclass

# Go's zero time.Time, which is what an unparseable stored timestamp
# round-trips to.
ZERO_TIME = "0001-01-01T00:00:00Z"

_RFC3339 = re.compile(
    r"^(\d{4}-\d{2}-\d{2}[Tt]\d{2}:\d{2}:\d{2})(\.\d+)?([Zz]|[+-]\d{2}:\d{2})$"
)


def _offset_text(seconds: int) -> str:
    if seconds == 0:
        return "Z"
    sign = "+" if seconds > 0 else "-"
    total = abs(seconds) // 60
    return f"{sign}{total // 60:02d}:{total % 60:02d}"


@dataclass(frozen=True, order=True)
class GoTime:
    unix_nano: int
    utc_offset: int = 0

    def format(self) -> str:
        sec, frac = divmod(self.unix_nano, 1_000_000_000)
        wall = datetime.datetime.fromtimestamp(sec + self.utc_offset, datetime.timezone.utc)
        out = wall.strftime("%Y-%m-%dT%H:%M:%S")
        if frac:
            # RFC3339Nano's ".999999999" drops trailing zeros, and drops the
            # separator entirely when the whole fraction is zero.
            out += ("." + f"{frac:09d}").rstrip("0")
        return out + _offset_text(self.utc_offset)


def now() -> GoTime:
    offset = datetime.datetime.now().astimezone().utcoffset()
    return GoTime(time.time_ns(), int(offset.total_seconds()) if offset else 0)


def normalize(text: str) -> str:
    """Go parses a stored timestamp and re-marshals it, so trailing fractional
    zeros come back trimmed and an unparseable value comes back as the zero
    time."""
    m = _RFC3339.match(text)
    if m is None:
        return ZERO_TIME
    frac = (m.group(2) or "").rstrip("0").rstrip(".")
    return m.group(1) + frac + m.group(3)
