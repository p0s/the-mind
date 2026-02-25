from __future__ import annotations

import csv
from pathlib import Path
from typing import Dict, Optional

from _core.notes_tokens import parse_notes_kv
from _core.timecodes import parse_timecode_to_seconds


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


def timecoded_url(url: str, timecode: str) -> str:
    sec = parse_timecode_to_seconds(timecode)
    if sec is None:
        return url
    u = (url or "").strip()
    if not u:
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

