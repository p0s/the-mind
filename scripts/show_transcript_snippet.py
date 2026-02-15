#!/usr/bin/env python3
"""
Show a small, local-only transcript window for a given source_id + timecode.

This is for internal verification only. Do not copy transcript text into
committed notes unless it's genuinely necessary and short.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, List, Optional, Tuple


ROOT = Path(__file__).resolve().parents[1]
INDEX_CSV = ROOT / "transcripts" / "_index.csv"
SPEAKERS_DIR = ROOT / "transcripts" / "_speakers"


def parse_hms(t: str) -> Optional[float]:
    m = re.match(r"^(\d{2}):(\d{2}):(\d{2})(?:[\.,](\d{1,3}))?$", t.strip())
    if not m:
        return None
    h, mm, ss, ms = m.groups()
    out = int(h) * 3600 + int(mm) * 60 + int(ss)
    if ms:
        out += int(ms.ljust(3, "0")) / 1000.0
    return out


def iter_vtt(path: Path) -> Iterator[Tuple[float, float, str]]:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if "-->" not in line:
            i += 1
            continue
        start_raw, end_raw = [p.strip() for p in line.split("-->", 1)]
        start_raw = start_raw.split()[0]
        end_raw = end_raw.split()[0]
        start = parse_hms(start_raw.replace(",", "."))
        end = parse_hms(end_raw.replace(",", "."))
        i += 1
        txt = []
        while i < len(lines):
            cur = lines[i].strip()
            if cur == "":
                i += 1
                break
            if "-->" in cur and re.match(r"^\d{2}:\d{2}:\d{2}", cur):
                break
            txt.append(cur)
            i += 1
        text = re.sub(r"<[^>]+>", "", " ".join(txt)).strip()
        text = re.sub(r"\\s+", " ", text)
        if start is not None and end is not None and text:
            yield start, end, text


def iter_srt(path: Path) -> Iterator[Tuple[float, float, str]]:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    i = 0
    while i < len(lines):
        if lines[i].strip().isdigit():
            i += 1
        if i >= len(lines):
            break
        time_line = lines[i].strip()
        if "-->" not in time_line:
            i += 1
            continue
        start_raw, end_raw = [p.strip() for p in time_line.split("-->", 1)]
        start = parse_hms(start_raw.replace(",", "."))
        end = parse_hms(end_raw.replace(",", "."))
        i += 1
        txt = []
        while i < len(lines) and lines[i].strip() != "":
            txt.append(lines[i].strip())
            i += 1
        i += 1
        text = re.sub(r"\\s+", " ", " ".join(txt)).strip()
        if start is not None and end is not None and text:
            yield start, end, text


def iter_segments(path: Path) -> Iterator[Tuple[float, float, str]]:
    suf = path.suffix.lower()
    if suf == ".vtt":
        yield from iter_vtt(path)
    elif suf == ".srt":
        yield from iter_srt(path)


def find_transcript_path(source_id: str) -> Optional[Path]:
    if not INDEX_CSV.exists():
        return None
    with INDEX_CSV.open("r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            if row.get("source_id") != source_id:
                continue
            rel = row.get("transcript_path", "")
            if not rel:
                return None
            p = ROOT / rel
            return p if p.exists() else None
    return None


def load_intervals(source_id: str, *, bach_only: bool, speaker: str) -> List[Tuple[float, float]]:
    if not bach_only and not speaker:
        return []
    path = SPEAKERS_DIR / f"{source_id}.speakers.json"
    if not path.exists():
        raise SystemExit(f"no speaker file for {source_id}: {path} (run scripts/diarize_bach.py)")
    data = json.loads(path.read_text(encoding="utf-8"))
    if bach_only:
        segs = data.get("bach_segments") or []
        out = [(float(s.get("start_s", 0.0)), float(s.get("end_s", 0.0))) for s in segs]
        return sorted(out)
    if speaker:
        segs = data.get("segments") or []
        out = [
            (float(s.get("start_s", 0.0)), float(s.get("end_s", 0.0)))
            for s in segs
            if (s.get("label") or "") == speaker
        ]
        return sorted(out)
    return []


def in_intervals(t: float, intervals: List[Tuple[float, float]]) -> bool:
    # Intervals are expected sorted by start time.
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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("source_id")
    ap.add_argument("timecode", help="HH:MM:SS[.mmm]")
    ap.add_argument("--window", type=float, default=20.0, help="Seconds before/after")
    ap.add_argument("--bach-only", action="store_true", help="Only show cues attributed to Bach (requires diarization file)")
    ap.add_argument("--speaker", default="", help="Only show cues for this diarized label (e.g. spk0)")
    args = ap.parse_args()

    t = parse_hms(args.timecode)
    if t is None:
        raise SystemExit(f"bad timecode: {args.timecode}")
    path = find_transcript_path(args.source_id)
    if path is None:
        raise SystemExit(f"no local transcript for {args.source_id}")

    lo = max(0.0, t - args.window)
    hi = t + args.window
    intervals = load_intervals(args.source_id, bach_only=bool(args.bach_only), speaker=(args.speaker or ""))
    print(f"{args.source_id}  {args.timecode}  ({path})")
    print("")

    for start, end, text in iter_segments(path):
        if end < lo:
            continue
        if start > hi:
            break
        if intervals:
            mid_t = 0.5 * (start + end)
            if not in_intervals(mid_t, intervals):
                continue
        if text:
            print(f"{start:8.2f}-{end:8.2f}: {text}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
