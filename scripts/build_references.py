#!/usr/bin/env python3
"""
Build reader-facing references from chapter anchor blocks.

This does not require transcripts and does not quote them; it just maps
source_id+timecode to the canonical URL/title in sources/sources.csv.
"""

from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Dict, List, Tuple


ROOT = Path(__file__).resolve().parents[1]
SOURCES_CSV = ROOT / "sources" / "sources.csv"
CHAPTERS_DIR = ROOT / "manuscript" / "chapters"
OUT = ROOT / "manuscript" / "references.md"


ANCHOR_RX = re.compile(r"^- ([^\s]+) @ (\d{2}:\d{2}:\d{2}) \(keywords: (.*)\)$")


def load_sources(path: Path) -> Dict[str, Dict[str, str]]:
    out: Dict[str, Dict[str, str]] = {}
    with path.open("r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            sid = row.get("source_id", "").strip()
            if sid:
                out[sid] = dict(row)
    return out


def parse_chapter_anchors(text: str) -> List[Tuple[str, str, str]]:
    lines = text.splitlines()
    out: List[Tuple[str, str, str]] = []
    in_block = False
    for line in lines:
        if line.strip() == "## Anchors (sources + timecodes)":
            in_block = True
            continue
        if in_block and line.startswith("## "):
            break
        if not in_block:
            continue
        m = ANCHOR_RX.match(line.strip())
        if not m:
            continue
        sid, tc, kw = m.groups()
        out.append((sid, tc, kw.strip()))
    return out


def main() -> int:
    sources = load_sources(SOURCES_CSV)

    chapters = sorted(CHAPTERS_DIR.glob("ch*.md"))
    parts: List[str] = []
    parts.append("# References")
    parts.append("")
    parts.append("Endnotes are keyed to the manuscript anchors: source id + timecode.")
    parts.append("")

    for ch_path in chapters:
        ch_text = ch_path.read_text(encoding="utf-8", errors="replace")
        # Chapter title is the first H1.
        ch_title = next((l[2:].strip() for l in ch_text.splitlines() if l.startswith("# ")), ch_path.stem)
        anchors = parse_chapter_anchors(ch_text)
        parts.append(f"## {ch_title}")
        if not anchors:
            parts.append("TBD.")
            parts.append("")
            continue

        # De-duplicate within chapter while preserving order.
        seen = set()
        uniq: List[Tuple[str, str, str]] = []
        for sid, tc, kw in anchors:
            key = (sid, tc)
            if key in seen:
                continue
            seen.add(key)
            uniq.append((sid, tc, kw))

        for sid, tc, kw in uniq:
            meta = sources.get(sid, {})
            title = meta.get("title", "").strip() or sid
            url = meta.get("url", "").strip()
            pub = meta.get("published_date", "").strip()
            creator = meta.get("creator_or_channel", "").strip()
            # Keep line readable and stable; avoid leaking any operational details.
            head = f"- {sid} @ {tc}"
            if pub:
                head += f" ({pub})"
            head += f": {title}"
            if creator:
                head += f" — {creator}"
            if url:
                head += f" — {url}"
            parts.append(head)
        parts.append("")

    OUT.write_text("\n".join(parts).rstrip() + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
