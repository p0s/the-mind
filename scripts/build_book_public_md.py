#!/usr/bin/env python3
"""
Build a reader-facing book Markdown.

Inputs:
- manuscript/chapters/*.md (drafting version; includes internal tags + hidden anchors)
- manuscript/references.md (reader-facing endnotes; already clean)

Output:
- manuscript/book_public.md

Transform rules:
- remove internal paragraph tags ([BACH]/[SYNTH]/[NOTE]/[OPEN])
- remove hidden per-paragraph anchors (HTML comments)
- rename "Anchors (sources + timecodes)" -> "References"
- strip internal "(keywords: ...)" from reference bullets
"""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHAPTERS_DIR = ROOT / "manuscript" / "chapters"
REFS_MD = ROOT / "manuscript" / "references.md"
OUT_MD = ROOT / "manuscript" / "book_public.md"


TAG_RX = re.compile(r"^\[(BACH|SYNTH|NOTE|OPEN)\]\s*", re.IGNORECASE)
SRC_COMMENT_RX = re.compile(r"\s*<!--\s*src:\s*[^>]+-->\s*$", re.IGNORECASE)
ANCHOR_HEADING_IN = "## Anchors (sources + timecodes)"
ANCHOR_HEADING_OUT = "## References"
ANCHOR_KEYWORDS_RX = re.compile(r"^(\s*-\s+[^\s]+\s+@\s+\d{2}:\d{2}:\d{2})\s+\(keywords:.*\)\s*$", re.IGNORECASE)


def transform(text: str) -> str:
    out_lines: list[str] = []
    for raw in text.splitlines():
        line = raw.rstrip("\n")

        if line.strip() == ANCHOR_HEADING_IN:
            out_lines.append(ANCHOR_HEADING_OUT)
            continue

        line = SRC_COMMENT_RX.sub("", line)
        line = TAG_RX.sub("", line)

        m = ANCHOR_KEYWORDS_RX.match(line)
        if m:
            line = m.group(1)

        out_lines.append(line)

    # Collapse excessive blank lines.
    normalized: list[str] = []
    blank = 0
    for line in out_lines:
        if line.strip() == "":
            blank += 1
            if blank > 1:
                continue
        else:
            blank = 0
        normalized.append(line)

    return "\n".join(normalized).rstrip() + "\n"


def main() -> int:
    chapters = sorted(CHAPTERS_DIR.glob("ch*.md"))
    if not chapters:
        raise SystemExit(f"no chapters under {CHAPTERS_DIR}")

    parts: list[str] = []
    parts.append("# the-mind\n")
    parts.append("A dense, definition-driven synthesis of how the mind works according to Joscha Bach.\n")
    parts.append("\n---\n")

    for ch in chapters:
        parts.append(transform(ch.read_text(encoding="utf-8", errors="replace")).rstrip() + "\n")
        parts.append("\n---\n")

    if REFS_MD.exists():
        parts.append(REFS_MD.read_text(encoding="utf-8", errors="replace").rstrip() + "\n")

    OUT_MD.write_text("\n".join(parts).strip() + "\n", encoding="utf-8")
    print(f"wrote {OUT_MD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
