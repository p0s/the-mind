#!/usr/bin/env python3
"""
Check that timecoded anchors in committed docs do not fall into non-Bach segments
for multi-speaker sources (using local-only diarization output).

This is a QA helper that reads:
- notes/claims.md
- manuscript/chapters/*.md

and checks anchors against:
- transcripts/_speakers/<source_id>.speakers.json  (gitignored)

It never reads or prints transcript text.
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple


ROOT = Path(__file__).resolve().parents[1]
SPEAKERS_DIR = ROOT / "transcripts" / "_speakers"
CLAIMS_MD = ROOT / "notes" / "claims.md"
CHAPTERS_DIR = ROOT / "manuscript" / "chapters"


@dataclass(frozen=True)
class Ref:
    source_id: str
    time_s: float
    timecode: str
    where: str


def parse_timecode(tc: str) -> Optional[float]:
    t = tc.strip().replace(",", ".")
    m = re.match(r"^(\d{2}):(\d{2}):(\d{2})(?:\.(\d{1,3}))?$", t)
    if not m:
        return None
    h, mm, ss, ms = m.groups()
    out = int(h) * 3600 + int(mm) * 60 + int(ss)
    if ms:
        out += int(ms.ljust(3, "0")) / 1000.0
    return float(out)


def iter_refs_from_claims(path: Path) -> Iterable[Ref]:
    rx = re.compile(r"^\s*-\s+([a-z0-9_\\-]+)\s+@\s+(\d{2}:\d{2}:\d{2}(?:[\\.,]\d{1,3})?)\b", re.I)
    for i, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1):
        m = rx.match(line)
        if not m:
            continue
        sid, tc = m.groups()
        t = parse_timecode(tc)
        if t is None:
            continue
        yield Ref(sid, t, tc.replace(",", "."), f"{path.name}:{i}")


def iter_refs_from_chapters(dir_path: Path) -> Iterable[Ref]:
    rx = re.compile(r"^\s*-\s+([a-z0-9_\\-]+)\s+@\s+(\d{2}:\d{2}:\d{2}(?:[\\.,]\d{1,3})?)\b", re.I)
    inline_rx = re.compile(
        r"<!--\s*src:\s*([a-z0-9_\\-]+)\s*@\s*(\d{2}:\d{2}:\d{2}(?:[\\.,]\d{1,3})?)\s*-->",
        re.I,
    )
    for path in sorted(dir_path.glob("ch*.md")):
        for i, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1):
            m = rx.match(line)
            if not m:
                # Also parse hidden per-paragraph anchors: <!-- src: ... @ ... -->
                for m2 in inline_rx.finditer(line):
                    sid, tc = m2.groups()
                    t = parse_timecode(tc)
                    if t is None:
                        continue
                    yield Ref(sid, t, tc.replace(",", "."), f"{path.name}:{i}")
                continue
            sid, tc = m.groups()
            t = parse_timecode(tc)
            if t is None:
                continue
            yield Ref(sid, t, tc.replace(",", "."), f"{path.name}:{i}")


def load_speaker_meta(source_id: str) -> Optional[dict]:
    path = SPEAKERS_DIR / f"{source_id}.speakers.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def load_bach_intervals(meta: dict) -> List[Tuple[float, float]]:
    segs = meta.get("bach_segments") or []
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


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--include-solo", action="store_true", help="Also check sources where multi_speaker_heuristic is false")
    args = ap.parse_args(argv)

    refs = list(iter_refs_from_claims(CLAIMS_MD)) + list(iter_refs_from_chapters(CHAPTERS_DIR))
    refs_by_source: Dict[str, List[Ref]] = {}
    for r in refs:
        refs_by_source.setdefault(r.source_id, []).append(r)

    total = 0
    bad: List[Tuple[str, Ref]] = []
    missing = 0
    missing_sources: List[Tuple[str, int]] = []
    skipped = 0

    for sid, items in sorted(refs_by_source.items()):
        meta = load_speaker_meta(sid)
        if meta is None:
            missing += 1
            missing_sources.append((sid, len(items)))
            continue
        multi = bool(meta.get("multi_speaker_heuristic"))
        if (not multi) and (not args.include_solo):
            skipped += 1
            continue
        intervals = load_bach_intervals(meta)
        if not intervals:
            continue
        for r in items:
            total += 1
            if not in_intervals(r.time_s, intervals):
                bad.append((sid, r))

    print("speaker_audit")
    print(f"  refs_total: {len(refs)}")
    print(f"  refs_checked: {total}")
    print(f"  sources_missing_speaker_file: {missing}")
    print(f"  sources_skipped_solo: {skipped}")
    print(f"  refs_outside_bach_segments: {len(bad)}")
    if missing_sources:
        print("")
        print("missing_speaker_files:")
        for sid, n in sorted(missing_sources, key=lambda t: (-t[1], t[0])):
            print(f"  - {sid} (refs: {n})")
    if bad:
        print("")
        print("outside_bach_segments:")
        for sid, r in bad:
            print(f"  - {sid} @ {r.timecode} ({r.where})")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
