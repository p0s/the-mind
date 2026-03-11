from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Dict, Optional

from _core.notes_tokens import parse_notes_kv
from _core.locators import locator_kind, normalize_locator, parse_pdf_page
from _core.timecodes import parse_timecode_to_seconds
from urllib.parse import urlparse


def load_sources_csv(path: Path) -> Dict[str, Dict[str, str]]:
    out: Dict[str, Dict[str, str]] = {}
    with path.open("r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            sid = (row.get("source_id") or "").strip()
            if not sid:
                continue
            out[sid] = dict(row)
    return out


def load_source_ids(path: Path) -> set[str]:
    return set(load_sources_csv(path).keys())


def sanitize_source_id_component(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    return s.strip("_")


def source_id_for_url(url: str) -> str:
    """
    Generate a deterministic `web_...` source_id for an arbitrary URL.

    Format: web_<host>_<path>

    - host: lowercased, "www." stripped, non-alphanumerics -> "_"
    - path: non-alphanumerics -> "_"; empty path -> "root"
    """
    p = urlparse(url or "")
    host = sanitize_source_id_component((p.hostname or "web").replace("www.", ""))
    path = sanitize_source_id_component(p.path.strip("/")) or "root"
    return f"web_{host}_{path}"


ALLOWED_PRESENTATION_FORMATS = {"talk", "interview", "essay"}


def normalize_presentation_format(v: str) -> Optional[str]:
    x = (v or "").strip().lower()
    if not x:
        return None
    if x in ALLOWED_PRESENTATION_FORMATS:
        return x
    if x in {"podcast", "conversation", "qa"}:
        return "interview"
    if x in {"lecture", "presentation", "keynote"}:
        return "talk"
    if x in {"article", "post", "blog"}:
        return "essay"
    return None


def infer_presentation_format(meta: Dict[str, str]) -> str:
    """
    A minimal, display-oriented classifier.

    If a `format=` token exists in notes, prefer it. Otherwise, use conservative heuristics.
    """
    notes = meta.get("notes") or ""
    kv = parse_notes_kv(notes)
    fmt = normalize_presentation_format(kv.get("format") or "")
    if fmt:
        return fmt

    kind = (meta.get("kind") or "").strip().lower()  # media type; do not display
    url = (meta.get("url") or "").strip().lower()
    title = (meta.get("title") or "").strip().lower()
    creator = (meta.get("creator_or_channel") or "").strip().lower()
    hay = " ".join([title, creator])

    if kind in {"web"}:
        return "essay"
    if "media.ccc.de" in url or kind in {"ccc"}:
        return "talk"
    if any(w in hay for w in ("interview", "podcast", "conversation", "salon", "debate", "q&a", "qa")):
        return "interview"
    if any(w in hay for w in ("lex fridman", "curt jaimungal", "street talk")):
        return "interview"
    return "talk"


def located_url(url: str, locator: str) -> str:
    """
    Return a canonical URL that locates into a source:
      - timecoded media: append a t=SECONDS query parameter where supported
      - PDFs: append a #page=N fragment (1-based)
    """
    u = (url or "").strip()
    if not u:
        return u

    loc = normalize_locator(locator)
    kind = locator_kind(loc)

    if kind == "pdf_page":
        page = parse_pdf_page(loc)
        if page is None:
            return u
        start, _end = page
        # Replace any existing fragment; page links should be deterministic.
        from urllib.parse import urlsplit, urlunsplit

        parts = urlsplit(u)
        parts = parts._replace(fragment=f"page={start}")
        return urlunsplit(parts)

    if kind == "timecode":
        sec = parse_timecode_to_seconds(loc)
        if sec is None:
            return u

        # YouTube
        if "youtube.com/watch" in u:
            join = "&" if "?" in u else "?"
            return f"{u}{join}t={sec}s"
        if "youtu.be/" in u:
            join = "&" if "?" in u else "?"
            return f"{u}{join}t={sec}"

        # media.ccc.de commonly supports ?t=SECONDS
        if "media.ccc.de" in u:
            join = "&" if "?" in u else "?"
            return f"{u}{join}t={sec}"

        return u

    return u


def timecoded_url(url: str, timecode: str) -> str:
    # Backward-compatible wrapper.
    return located_url(url, timecode)
