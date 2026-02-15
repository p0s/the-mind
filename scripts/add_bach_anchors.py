#!/usr/bin/env python3
"""
Inject hidden source anchors into [BACH] blocks in manuscript chapters.

Spec requirement (internal): every [BACH] paragraph/block must be anchored.
We attach anchors as HTML comments to avoid cluttering reader-facing prose:

  [BACH] ... <!-- src: yt_xxx @ 00:00:00 -->

Anchors are chosen from the chapter's existing "Anchors (sources + timecodes)"
section, using a simple keyword-overlap heuristic with a small amount of local
context (the tagged line + following non-empty lines).
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple


ROOT = Path(__file__).resolve().parents[1]
CHAPTERS_DIR = ROOT / "manuscript" / "chapters"


ANCHOR_RX = re.compile(
    r"^\s*-\s+([a-z0-9_\-]+)\s+@\s+(\d{2}:\d{2}:\d{2})\s+\(keywords:\s*(.*?)\)\s*$",
    re.IGNORECASE,
)
BACH_LINE_RX = re.compile(r"^\[BACH\]")
HAS_SRC_RX = re.compile(r"<!--\s*src:\s*[^>]+-->")


STOPWORDS = {
    "a",
    "an",
    "and",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "the",
    "to",
    "with",
}


@dataclass(frozen=True)
class Anchor:
    source_id: str
    timecode: str
    keywords: List[str]


def tokenize_keywords(s: str) -> List[str]:
    raw = re.split(r"[,\s]+", s.strip().lower())
    out: List[str] = []
    for tok in raw:
        tok = tok.strip()
        if not tok:
            continue
        if tok in STOPWORDS:
            continue
        out.append(tok)
    return out


def score_anchor(context: str, a: Anchor) -> int:
    ctx = context.lower()
    score = 0
    for kw in a.keywords:
        if kw and kw in ctx:
            score += 1
    return score


def load_chapter_anchors(lines: List[str]) -> List[Anchor]:
    anchors: List[Anchor] = []
    in_anchors = False
    for line in lines:
        if line.strip() == "## Anchors (sources + timecodes)":
            in_anchors = True
            continue
        if in_anchors and line.startswith("## "):
            break
        if not in_anchors:
            continue
        m = ANCHOR_RX.match(line)
        if not m:
            continue
        sid, tc, kws = m.groups()
        anchors.append(Anchor(sid, tc, tokenize_keywords(kws)))
    return anchors


def context_for_bach_line(lines: List[str], i: int, max_follow: int = 10) -> str:
    # Start with the current line, stripped of the tag and any HTML comment.
    cur = lines[i]
    cur = re.sub(r"^\[BACH\]\s*", "", cur).strip()
    cur = re.sub(r"<!--.*?-->", "", cur).strip()

    ctx_parts: List[str] = [cur] if cur else []

    # Include a few following lines (until a blank line / next tag / next heading).
    for j in range(i + 1, min(len(lines), i + 1 + max_follow)):
        nxt = lines[j].rstrip("\n")
        if not nxt.strip():
            break
        if nxt.startswith(("## ", "# ")):
            break
        if nxt.startswith(("[BACH]", "[SYNTH]", "[NOTE]", "[OPEN]")):
            break
        # Include bullet items and normal text; strip code fences as hard stops.
        if nxt.strip().startswith("```"):
            break
        ctx_parts.append(nxt.strip())

    return " ".join(ctx_parts).strip()


def choose_anchor(context: str, anchors: List[Anchor]) -> Anchor:
    if not anchors:
        raise RuntimeError("chapter has no anchors section")
    best = anchors[0]
    best_score = -1
    for a in anchors:
        s = score_anchor(context, a)
        if s > best_score:
            best = a
            best_score = s
    return best


def process_chapter(path: Path) -> Tuple[bool, int, int]:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    anchors = load_chapter_anchors(lines)
    if not anchors:
        return False, 0, 0

    changed = False
    total_bach = 0
    anchored = 0

    for i, line in enumerate(lines):
        if not BACH_LINE_RX.match(line):
            continue
        total_bach += 1
        if HAS_SRC_RX.search(line):
            anchored += 1
            continue
        ctx = context_for_bach_line(lines, i)
        a = choose_anchor(ctx, anchors)
        suffix = f" <!-- src: {a.source_id} @ {a.timecode} -->"
        lines[i] = line.rstrip() + suffix
        anchored += 1
        changed = True

    if changed:
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return changed, total_bach, anchored


def main(argv: List[str]) -> int:
    paths = sorted(CHAPTERS_DIR.glob("ch*.md"))
    if not paths:
        print("no chapters found", file=sys.stderr)
        return 2

    changed_any = False
    total_bach = 0
    total_anchored = 0
    for p in paths:
        changed, bach, anchored = process_chapter(p)
        changed_any = changed_any or changed
        total_bach += bach
        total_anchored += anchored

    print("add_bach_anchors")
    print(f"  chapters: {len(paths)}")
    print(f"  bach_blocks: {total_bach}")
    print(f"  anchored_blocks: {total_anchored}")
    print(f"  changed: {bool(changed_any)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
