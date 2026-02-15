#!/usr/bin/env python3
"""
Generate lightweight, non-quoting source notes from local transcripts.

Notes are committed; transcripts are not. To avoid attribution and copyright
issues, this script never copies transcript text into source notes. Instead it
lists timecoded segments with keyword tags only.
"""

from __future__ import annotations

import argparse
import csv
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple
import json


ROOT = Path(__file__).resolve().parents[1]
SOURCES_CSV = ROOT / "sources" / "sources.csv"
INDEX_CSV = ROOT / "transcripts" / "_index.csv"
OUT_DIR = ROOT / "sources" / "source_notes"
SPEAKERS_DIR = ROOT / "transcripts" / "_speakers"


KEYWORDS = [
    "world model",
    "world-model",
    "representation",
    "model",
    "simulate",
    "simulation",
    "predict",
    "prediction",
    "compression",
    "understanding",
    "agent",
    "agency",
    "control system",
    "control",
    "controller",
    "policy",
    "goal",
    "value",
    "valence",
    "reward",
    "emotion",
    "affect",
    "motivation",
    "self-model",
    "self model",
    "first-person",
    "observer",
    "narrative",
    "identity",
    "metacognition",
    "attention",
    "working memory",
    "workspace",
    "global workspace",
    "consciousness",
    "phenomenology",
    "mechanism",
    "function",
    "experience",
    "learning",
    "reinforcement",
    "prediction error",
    "error signal",
    "planning",
    "intelligence",
    "alignment",
    "ethics",
    "culture",
    "language",
    "social",
    "coordination",
    "norm",
    "contract",
]


def load_sources(path: Path) -> Dict[str, Dict[str, str]]:
    out: Dict[str, Dict[str, str]] = {}
    with path.open("r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            sid = row.get("source_id", "").strip()
            if sid:
                out[sid] = dict(row)
    return out


def load_index(path: Path) -> Dict[str, Dict[str, str]]:
    if not path.exists():
        return {}
    out: Dict[str, Dict[str, str]] = {}
    with path.open("r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            sid = row.get("source_id", "").strip()
            if sid:
                out[sid] = dict(row)
    return out


def parse_timecode(tc: str) -> Optional[float]:
    m = re.match(r"^(\d+):(\d+):(\d+)[\.,](\d+)$", tc.strip())
    if not m:
        return None
    h, mnt, s, ms = m.groups()
    return int(h) * 3600 + int(mnt) * 60 + int(s) + int(ms) / 1000.0


def format_timecode(seconds: float) -> str:
    if seconds < 0:
        seconds = 0.0
    total_ms = int(round(seconds * 1000))
    h, rem = divmod(total_ms, 3600_000)
    m, rem = divmod(rem, 60_000)
    s, _ = divmod(rem, 1000)
    return f"{h:02}:{m:02}:{s:02}"


def iter_vtt(path: Path) -> Iterable[Tuple[float, float, str]]:
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
        start = parse_timecode(start_raw.replace(",", "."))
        end = parse_timecode(end_raw.replace(",", "."))
        i += 1
        txt_lines: List[str] = []
        while i < len(lines):
            cur = lines[i].strip()
            if cur == "":
                i += 1
                break
            if "-->" in cur:
                # Next cue starts without a blank line.
                break
            txt_lines.append(cur)
            i += 1
        text = " ".join(txt_lines)
        text = re.sub(r"<[^>]+>", "", text)
        text = re.sub(r"\\s+", " ", text).strip()
        if start is not None:
            yield start, end or start, text


def iter_srt(path: Path) -> Iterable[Tuple[float, float, str]]:
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
        start = parse_timecode(start_raw.replace(",", "."))
        end = parse_timecode(end_raw.replace(",", "."))
        i += 1
        txt_lines: List[str] = []
        while i < len(lines):
            cur = lines[i].strip()
            if cur == "":
                i += 1
                break
            if "-->" in cur and re.match(r"^\d{2}:\d{2}:\d{2}", cur):
                break
            txt_lines.append(cur)
            i += 1
        text = " ".join(txt_lines).strip()
        if start is not None:
            yield start, end or start, text


def iter_html(path: Path) -> Iterable[Tuple[float, float, str]]:
    html = path.read_text(encoding="utf-8", errors="replace")
    text = re.sub(r"<script\\b.*?</script>", " ", html, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<style\\b.*?</style>", " ", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\\s+", " ", text).strip()
    if text:
        yield 0.0, 0.0, text


def iter_segments(path: Path) -> Iterable[Tuple[float, float, str]]:
    suf = path.suffix.lower()
    if suf == ".vtt":
        yield from iter_vtt(path)
    elif suf == ".srt":
        yield from iter_srt(path)
    elif suf == ".html":
        yield from iter_html(path)
    else:
        return


def keyword_hits(text: str, keywords: List[str]) -> List[str]:
    t = text.lower()
    hits = []
    for kw in keywords:
        if kw in t:
            hits.append(kw)
    return hits


def top_segments(
    segments: List[Tuple[float, float, str]],
    keywords: List[str],
    max_segments: int,
    min_gap_s: int,
) -> List[Tuple[float, float, List[str]]]:
    scored: List[Tuple[int, float, float, List[str]]] = []
    for start, end, text in segments:
        hits = keyword_hits(text, keywords)
        if not hits:
            continue
        score = sum(max(1, len(h.split())) for h in hits)
        scored.append((score, start, end, hits))
    scored.sort(key=lambda x: (-x[0], x[1]))

    picked: List[Tuple[float, float, List[str]]] = []
    for score, start, end, hits in scored:
        if len(picked) >= max_segments:
            break
        if any(abs(start - ps) < min_gap_s for ps, _, _ in picked):
            continue
        picked.append((start, end, hits))
    picked.sort(key=lambda x: x[0])
    return picked


def top_keywords(segments: List[Tuple[float, float, str]], keywords: List[str], limit: int = 8) -> List[str]:
    counts: Dict[str, int] = {k: 0 for k in keywords}
    for _, _, text in segments:
        t = text.lower()
        for kw in keywords:
            if kw in t:
                counts[kw] += 1
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return [k for k, v in ranked if v > 0][:limit]


def render_note(
    source_id: str,
    meta: Dict[str, str],
    selected_segments: List[Tuple[float, float, List[str]]],
    dominant_terms: List[str],
) -> str:
    title = meta.get("title", "").strip() or "Untitled"
    kind = meta.get("kind", "").strip()
    creator = meta.get("creator_or_channel", "").strip()
    published = meta.get("published_date", "").strip()
    url = meta.get("url", "").strip()
    lang = meta.get("language", "").strip()

    lines: List[str] = []
    lines.append(f"# {source_id} — {title}")
    lines.append("")
    lines.append("## Metadata")
    if kind:
        lines.append(f"- Kind: {kind}")
    if creator:
        lines.append(f"- Creator/channel: {creator}")
    if published:
        lines.append(f"- Published: {published}")
    if url:
        lines.append(f"- URL: {url}")
    if lang:
        lines.append(f"- Language: {lang}")
    lines.append("")
    lines.append("## One-paragraph summary")
    if dominant_terms:
        terms = ", ".join(dominant_terms)
        lines.append(f"AUTO (keyword-based): dominant terms include {terms}.")
    else:
        lines.append("TBD.")
    lines.append("")
    lines.append("## Key segments (timecodes)")
    if selected_segments:
        for start, end, hits in selected_segments:
            tc = format_timecode(start)
            tc_end = format_timecode(end)
            hits_s = ", ".join(sorted(set(hits)))
            lines.append(f"- [{tc}-{tc_end}] keywords: {hits_s}")
    else:
        lines.append("TBD.")
    lines.append("")
    lines.append("## Terms to add to glossary")
    lines.append("TBD.")
    lines.append("")
    lines.append("## Candidate claims to add to claim ledger")
    lines.append("TBD.")
    lines.append("")
    return "\n".join(lines)


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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sources", default=str(SOURCES_CSV), help="Path to sources.csv")
    ap.add_argument("--index", default=str(INDEX_CSV), help="Path to transcripts/_index.csv")
    ap.add_argument("--out-dir", default=str(OUT_DIR), help="Output directory for source notes")
    ap.add_argument("--source-id", action="append", help="Limit to specific source_id (repeatable)")
    ap.add_argument("--bach-only", action="store_true", help="If diarization exists, only use Bach-attributed cues")
    ap.add_argument("--max-segments", type=int, default=8, help="Max segments to list per source")
    ap.add_argument("--min-gap", type=int, default=60, help="Min seconds between listed segments")
    ap.add_argument("--max-text-chars", type=int, default=500, help="Skip cues longer than this many chars")
    ap.add_argument("--force", action="store_true", help="Overwrite existing notes")
    args = ap.parse_args()

    sources = load_sources(Path(args.sources))
    index = load_index(Path(args.index))
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    want = set(args.source_id or [])
    for sid, meta in sources.items():
        if want and sid not in want:
            continue
        out_path = out_dir / f"{sid}.md"
        if out_path.exists() and not args.force:
            continue
        idx = index.get(sid)
        if not idx or idx.get("status") != "ok":
            continue
        rel = idx.get("transcript_path", "")
        if not rel:
            continue
        transcript_path = ROOT / rel
        if not transcript_path.exists():
            continue

        segments = [s for s in iter_segments(transcript_path) if len(s[2]) <= args.max_text_chars]
        if args.bach_only:
            intervals = load_bach_intervals(sid)
            if intervals:
                segments = [s for s in segments if in_intervals(0.5 * (s[0] + s[1]), intervals)]
        dominant = top_keywords(segments, KEYWORDS)
        selected = top_segments(segments, KEYWORDS, args.max_segments, args.min_gap)
        note = render_note(sid, meta, selected, dominant)
        out_path.write_text(note, encoding="utf-8")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
