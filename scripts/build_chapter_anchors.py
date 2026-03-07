#!/usr/bin/env python3
"""
Populate chapter anchor sections from source_notes keyword segments.

This avoids quoting transcripts and only writes source_id + timecode + keyword tags.
"""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

from _core.notes_tokens import parse_notes_kv
from _core.locators import normalize_locator, valid_locator
from _core.sources import load_sources_csv


ROOT = Path(__file__).resolve().parents[1]
SOURCES_CSV = ROOT / "sources" / "sources.csv"
NOTES_DIR = ROOT / "sources" / "source_notes"
CHAPTERS_DIR = ROOT / "manuscript" / "chapters"


@dataclass(frozen=True)
class Segment:
    source_id: str
    locator: str
    keywords: Tuple[str, ...]
    published_date: str
    tier: str


def parse_date_key(s: str) -> Tuple[int, int, int]:
    if not s:
        return (0, 0, 0)
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", s.strip())
    if not m:
        return (0, 0, 0)
    return (int(m.group(1)), int(m.group(2)), int(m.group(3)))


def load_sources(path: Path) -> Dict[str, Dict[str, str]]:
    return load_sources_csv(path)


def iter_segments(
    notes_dir: Path,
    sources: Dict[str, Dict[str, str]],
    include_web: bool,
    keep_only: bool,
) -> Iterable[Segment]:
    rx = re.compile(r"^- \[(.+?)\]\s+keywords:\s*(.+)$", re.IGNORECASE)
    for path in sorted(notes_dir.glob("*.md")):
        sid = path.stem
        meta = sources.get(sid, {})
        notes = meta.get("notes", "") or ""
        kv = parse_notes_kv(notes)
        if keep_only and "curation_status=keep" not in notes:
            continue
        if not include_web and meta.get("kind") == "web":
            continue
        tier = (kv.get("tier") or "").strip() or "supporting"
        published = meta.get("published_date", "")
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            m = rx.match(line.strip())
            if not m:
                continue
            span, keys = m.groups()
            span = (span or "").strip()
            if re.match(r"^\d{2}:\d{2}:\d{2}", span):
                # Time ranges: [HH:MM:SS-HH:MM:SS] -> anchor at start
                start = span.split("-", 1)[0].strip()
                locator = normalize_locator(start)
            else:
                # Page locators: [p16] or [p19-20]
                locator = normalize_locator(span)
            if not valid_locator(locator):
                continue
            kw = tuple(k.strip() for k in keys.split(",") if k.strip())
            if not kw:
                continue
            yield Segment(sid, locator, kw, published, tier)


def pick_segments(
    segments: List[Segment],
    chapter_keywords: List[str],
    max_items: int,
    max_per_source: int,
) -> List[Segment]:
    kw_set = {k.lower() for k in chapter_keywords}
    tier_weight = {"keystone": 3, "supporting": 2, "legacy": 1, "aux": 0}
    scored: List[Tuple[int, int, Tuple[int, int, int], Segment]] = []
    for seg in segments:
        hits = [k for k in seg.keywords if k.lower() in kw_set]
        if not hits:
            continue
        score = len(hits)
        scored.append((tier_weight.get(seg.tier, 1), score, parse_date_key(seg.published_date), seg))

    scored.sort(key=lambda x: (-x[0], -x[1], -x[2][0], -x[2][1], -x[2][2], x[3].locator))

    picked: List[Segment] = []
    per_source: Dict[str, int] = {}
    for _, _, _, seg in scored:
        if len(picked) >= max_items:
            break
        count = per_source.get(seg.source_id, 0)
        if count >= max_per_source:
            continue
        per_source[seg.source_id] = count + 1
        picked.append(seg)
    return picked


def update_chapter(path: Path, anchors: List[Segment]) -> None:
    header = "## Anchors (sources + timecodes)"
    content = path.read_text(encoding="utf-8", errors="replace")
    if not anchors:
        replacement = header + "\nTBD.\n"
    else:
        lines = [header]
        for seg in anchors:
            kw = ", ".join(seg.keywords)
            lines.append(f"- {seg.source_id} @ {seg.locator} (keywords: {kw})")
        replacement = "\n".join(lines) + "\n"

    pattern = re.compile(r"## Anchors \(sources \+ timecodes\)\n.*?(?=\n## |\Z)", re.S)
    new_content, n = pattern.subn(replacement, content)
    if n == 0:
        new_content = content.rstrip() + "\n\n" + replacement
    path.write_text(new_content, encoding="utf-8")


CHAPTER_KEYWORDS_RX = re.compile(r"<!--\s*chapter_keywords:\s*(.*?)\s*-->", re.IGNORECASE)


def parse_chapter_keywords(md: str) -> List[str]:
    m = CHAPTER_KEYWORDS_RX.search(md or "")
    if not m:
        return []
    raw = m.group(1)
    out: List[str] = []
    for piece in raw.split(","):
        k = piece.strip()
        if k:
            out.append(k)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-items", type=int, default=8, help="Max anchors per chapter")
    ap.add_argument("--max-per-source", type=int, default=2, help="Max anchors per source")
    ap.add_argument("--include-web", action="store_true", help="Allow web sources (no real timecodes)")
    ap.add_argument("--keep-only", action="store_true", help="Only use sources with curation_status=keep")
    args = ap.parse_args()

    sources = load_sources(SOURCES_CSV)
    segments = list(iter_segments(NOTES_DIR, sources, include_web=args.include_web, keep_only=args.keep_only))

    paths = sorted(CHAPTERS_DIR.glob("ch*.md"))
    for path in paths:
        md = path.read_text(encoding="utf-8", errors="replace")
        keywords = parse_chapter_keywords(md)
        if not keywords:
            raise SystemExit(
                f"Missing chapter keywords metadata in {path.relative_to(ROOT)}. Add: <!-- chapter_keywords: kw1, kw2, ... -->"
            )
        anchors = pick_segments(segments, keywords, args.max_items, args.max_per_source)
        update_chapter(path, anchors)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
