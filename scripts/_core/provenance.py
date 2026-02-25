from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from _core.timecodes import normalize_timecode


SOURCE_ID_RX = re.compile(r"^[a-z0-9_\-]+$", re.IGNORECASE)
_SRC_COMMENT_ANY_RX = re.compile(r"<!--\s*src:\s*.*?-->", re.IGNORECASE)
_SRC_COMMENT_EOL_RX = re.compile(r"<!--\s*src:\s*(.*?)-->\s*$", re.IGNORECASE)

_SRC_REF_RX = re.compile(
    r"^\s*([a-z0-9_\-]+)\s*@\s*(\d{2}:\d{2}:\d{2}(?:[.,]\d{1,3})?)\s*$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class SrcComment:
    refs: Tuple[Tuple[str, str], ...]  # (source_id, timecode)
    meta: Tuple[Tuple[str, str], ...]  # key-value tokens (stable order)

    @property
    def meta_dict(self) -> Dict[str, str]:
        return dict(self.meta)


def find_src_comments(line: str) -> List[str]:
    return _SRC_COMMENT_ANY_RX.findall(line or "")


def parse_src_ref(token: str) -> Optional[Tuple[str, str]]:
    m = _SRC_REF_RX.match(token or "")
    if not m:
        return None
    sid = m.group(1).strip()
    tc = normalize_timecode(m.group(2))
    return (sid, tc)


def parse_src_comment_payload(payload: str) -> Optional[SrcComment]:
    """
    Parse the inside of `<!-- src: ... -->` after `src:`.

    Supported:
      - one or more refs: `sid @ tc; sid2 @ tc`
      - optional metadata after `|`: `... | auto=needs_review score=1`
    """
    raw = (payload or "").strip()
    if not raw:
        return None

    if "|" in raw:
        refs_part, meta_part = raw.split("|", 1)
        meta_part = meta_part.strip()
    else:
        refs_part, meta_part = raw, ""

    refs: List[Tuple[str, str]] = []
    for piece in (p.strip() for p in refs_part.split(";")):
        if not piece:
            continue
        ref = parse_src_ref(piece)
        if not ref:
            return None
        refs.append(ref)

    if not refs:
        return None

    meta: Dict[str, str] = {}
    for tok in meta_part.split():
        if "=" not in tok:
            continue
        k, v = tok.split("=", 1)
        k = k.strip()
        v = v.strip()
        if k and v:
            meta[k] = v

    meta_items = tuple(sorted(meta.items(), key=lambda kv: kv[0].lower()))
    return SrcComment(refs=tuple(refs), meta=meta_items)


def parse_src_comment_eol(line: str) -> Optional[SrcComment]:
    """
    If `line` ends with a src comment, parse it.
    """
    m = _SRC_COMMENT_EOL_RX.search(line or "")
    if not m:
        return None
    payload = (m.group(1) or "").strip()
    return parse_src_comment_payload(payload)


def strip_src_comment_eol(line: str) -> Tuple[str, Optional[SrcComment]]:
    """
    Remove an end-of-line src comment, if present, and return (stripped_text, parsed_comment).
    """
    m = _SRC_COMMENT_EOL_RX.search(line or "")
    if not m:
        return (line or ""), None
    comment = parse_src_comment_payload((m.group(1) or "").strip())
    # Remove the whole comment.
    stripped = (line[: m.start()]).rstrip()
    return stripped, comment


def format_src_comment(
    refs: Sequence[Tuple[str, str]],
    *,
    meta: Optional[Dict[str, str]] = None,
) -> str:
    """
    Format a canonical `<!-- src: ... -->` comment.
    """
    parts = [f"{sid} @ {normalize_timecode(tc)}" for sid, tc in refs]
    inner = "; ".join(parts)
    meta = meta or {}
    if meta:
        meta_txt = " ".join([f"{k}={v}" for k, v in sorted(meta.items(), key=lambda kv: kv[0].lower())])
        inner = f"{inner} | {meta_txt}"
    return f"<!-- src: {inner} -->"

