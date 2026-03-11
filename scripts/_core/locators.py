from __future__ import annotations

import re
from typing import Literal, Optional, Tuple

from _core.timecodes import normalize_timecode, valid_timecode


_PDF_PAGE_LOOSE_RX = re.compile(r"^p\.?\s*(\d+)(?:\s*[-–—]\s*(\d+))?$", re.IGNORECASE)
_PDF_PAGE_CANON_RX = re.compile(r"^p(\d+)(?:-(\d+))?$", re.IGNORECASE)


def normalize_locator(raw: str) -> str:
    """
    Normalize a locator string into a canonical form.

    Supported:
      - Timecode: HH:MM:SS[.mmm]
      - PDF page: pN or pN-M
    """
    s = (raw or "").strip()
    if not s:
        return ""

    # Timecode
    tc = normalize_timecode(s)
    if valid_timecode(tc):
        return tc

    # PDF page locator
    s = s.replace("–", "-").replace("—", "-")
    m = _PDF_PAGE_LOOSE_RX.match(s)
    if not m:
        return s
    start_s, end_s = m.groups()
    try:
        start = int(start_s)
        end = int(end_s) if end_s is not None else None
    except Exception:
        return s
    if end is None:
        return f"p{start}"
    return f"p{start}-{end}"


def parse_pdf_page(raw: str) -> Optional[Tuple[int, int]]:
    loc = normalize_locator(raw)
    m = _PDF_PAGE_CANON_RX.match(loc)
    if not m:
        return None
    start_s, end_s = m.groups()
    try:
        start = int(start_s)
        end = int(end_s) if end_s is not None else start
    except Exception:
        return None
    if start < 1 or end < start:
        return None
    return (start, end)


def locator_kind(raw: str) -> Literal["timecode", "pdf_page", "unknown"]:
    loc = normalize_locator(raw)
    if valid_timecode(loc):
        return "timecode"
    if parse_pdf_page(loc) is not None:
        return "pdf_page"
    return "unknown"


def valid_locator(raw: str) -> bool:
    kind = locator_kind(raw)
    return kind != "unknown"

