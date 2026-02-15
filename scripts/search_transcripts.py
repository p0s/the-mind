#!/usr/bin/env python3
"""
Quick grep-like search across local transcripts (transcripts/_index.csv).

This is intentionally simple and local-only:
- It reads VTT/SRT cues and prints matching segments with timecodes.
- It can also search downloaded HTML for web sources (no timecodes).
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Optional, Tuple


ROOT = Path(__file__).resolve().parents[1]
INDEX_CSV = ROOT / "transcripts" / "_index.csv"
SPEAKERS_DIR = ROOT / "transcripts" / "_speakers"


@dataclass(frozen=True)
class Hit:
    source_id: str
    kind: str
    timecode: str  # may be empty for non-timecoded sources
    text: str
    path: Path


def eprint(*args: object) -> None:
    print(*args, file=sys.stderr)


def iter_vtt(path: Path) -> Iterator[tuple[str, str]]:
    # Minimal WebVTT parser: cue lines contain "-->".
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if "-->" not in line:
            i += 1
            continue
        start = line.split("-->", 1)[0].strip()
        # Collect cue text until blank line.
        i += 1
        txt_lines: list[str] = []
        while i < len(lines) and lines[i].strip() != "":
            l = lines[i].strip()
            if l and not l.startswith(("NOTE", "WEBVTT")):
                txt_lines.append(l)
            i += 1
        text = " ".join(txt_lines).strip()
        # yt-dlp WebVTT often contains inline timestamps and <c> spans; strip tags.
        text = re.sub(r"<[^>]+>", "", text)
        text = re.sub(r"\s+", " ", text).strip()
        yield start, text
        i += 1


def iter_srt(path: Path) -> Iterator[tuple[str, str]]:
    # Minimal SRT parser.
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    i = 0
    while i < len(lines):
        # Skip cue number.
        if lines[i].strip().isdigit():
            i += 1
        if i >= len(lines):
            break
        time_line = lines[i].strip()
        if "-->" not in time_line:
            i += 1
            continue
        start = time_line.split("-->", 1)[0].strip()
        i += 1
        txt_lines: list[str] = []
        while i < len(lines) and lines[i].strip() != "":
            txt_lines.append(lines[i].strip())
            i += 1
        yield start, " ".join(txt_lines).strip()
        i += 1


def iter_html(path: Path) -> Iterator[tuple[str, str]]:
    # No timecodes; just return chunks of visible-ish text.
    html = path.read_text(encoding="utf-8", errors="replace")
    # Strip tags crudely.
    text = re.sub(r"<script\b.*?</script>", " ", html, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<style\b.*?</style>", " ", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    # Chunk to keep output readable.
    for m in re.finditer(r".{1,240}", text):
        yield "", m.group(0).strip()


def iter_segments(path: Path) -> Iterator[tuple[str, str]]:
    suf = path.suffix.lower()
    if suf == ".vtt":
        yield from iter_vtt(path)
    elif suf == ".srt":
        yield from iter_srt(path)
    elif suf == ".html":
        yield from iter_html(path)
    else:
        return


def parse_timecode_start(tc: str) -> Optional[float]:
    # VTT: "HH:MM:SS.mmm" or "HH:MM:SS"
    # SRT: "HH:MM:SS,mmm"
    if not tc:
        return None
    t = tc.strip().split()[0].replace(",", ".")
    m = re.match(r"^(\d{2}):(\d{2}):(\d{2})(?:\.(\d{1,3}))?$", t)
    if not m:
        return None
    h, mm, ss, ms = m.groups()
    out = int(h) * 3600 + int(mm) * 60 + int(ss)
    if ms:
        out += int(ms.ljust(3, "0")) / 1000.0
    return float(out)


def load_bach_intervals(source_id: str) -> List[Tuple[float, float]]:
    path = SPEAKERS_DIR / f"{source_id}.speakers.json"
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    segs = data.get("bach_segments") or []
    out: List[Tuple[float, float]] = []
    for s in segs:
        try:
            out.append((float(s.get("start_s", 0.0)), float(s.get("end_s", 0.0))))
        except Exception:
            continue
    out.sort(key=lambda t: t[0])
    return out


def in_intervals(t: float, intervals: List[Tuple[float, float]]) -> bool:
    lo, hi = 0, len(intervals) - 1
    while lo <= hi:
        mid = (lo + hi) // 2
        s, e = intervals[mid]
        if t < s:
            hi = mid - 1
        elif t > e:
            lo = mid + 1
        else:
            return True
    return False


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("query", help="Regex (case-insensitive by default)")
    ap.add_argument("--index", default=str(INDEX_CSV), help="Path to transcripts/_index.csv")
    ap.add_argument("--kinds", default="", help="Comma-separated kinds to search (youtube,ccc,web)")
    ap.add_argument("--max-hits", type=int, default=200, help="Stop after N hits")
    ap.add_argument("--case-sensitive", action="store_true", help="Use case-sensitive regex")
    ap.add_argument(
        "--bach-only",
        action="store_true",
        help="If diarization exists for a source, only match within Bach-attributed segments",
    )
    args = ap.parse_args(argv)

    index_path = Path(args.index)
    if not index_path.exists():
        eprint(f"missing index: {index_path}")
        return 2

    flags = 0 if args.case_sensitive else re.IGNORECASE
    rx = re.compile(args.query, flags)

    wanted = {k.strip() for k in args.kinds.split(",") if k.strip()}
    hits = 0
    bach_cache: Dict[str, List[Tuple[float, float]]] = {}

    with index_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("status") != "ok":
                continue
            kind = row.get("kind", "")
            if wanted and kind not in wanted:
                continue
            sid = row.get("source_id", "")
            rel = row.get("transcript_path", "")
            if not sid or not rel:
                continue
            path = ROOT / rel
            if not path.exists():
                continue
            intervals: List[Tuple[float, float]] = []
            if args.bach_only:
                intervals = bach_cache.get(sid)
                if intervals is None:
                    intervals = []
                if sid not in bach_cache:
                    intervals = load_bach_intervals(sid)
                    bach_cache[sid] = intervals
            for tc, text in iter_segments(path):
                if not text:
                    continue
                if args.bach_only and intervals:
                    t0 = parse_timecode_start(tc)
                    if t0 is not None and not in_intervals(t0, intervals):
                        continue
                if rx.search(text):
                    snippet = text
                    if len(snippet) > 240:
                        snippet = snippet[:237] + "..."
                    print(f"{sid}\t{tc}\t{snippet}")
                    hits += 1
                    if hits >= args.max_hits:
                        return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
