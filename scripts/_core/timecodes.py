from __future__ import annotations

import re
from typing import Optional


_TIME_RX = re.compile(r"^(\d{2}):(\d{2}):(\d{2})(?:[.,](\d{1,3}))?$")


def normalize_timecode(tc: str) -> str:
    return (tc or "").strip().replace(",", ".")


def valid_timecode(tc: str) -> bool:
    m = _TIME_RX.match(normalize_timecode(tc))
    if not m:
        return False
    _h, mm, ss, ms = m.groups()
    try:
        if int(mm) >= 60 or int(ss) >= 60:
            return False
        if ms is not None and int(ms) >= 1000:
            return False
    except Exception:
        return False
    return True


def parse_timecode_to_seconds(tc: str) -> Optional[int]:
    m = _TIME_RX.match(normalize_timecode(tc))
    if not m:
        return None
    h, mm, ss, _ms = m.groups()
    return int(h) * 3600 + int(mm) * 60 + int(ss)


def seconds_to_hhmmss(total_s: int) -> str:
    s = max(0, int(total_s))
    h = s // 3600
    s -= h * 3600
    m = s // 60
    s -= m * 60
    return f"{h:02d}:{m:02d}:{s:02d}"

