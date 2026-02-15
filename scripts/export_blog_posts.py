#!/usr/bin/env python3
"""
Export manuscript chapters as standalone series posts.

This is a *presentation* transform:
- strips internal drafting tags ([BACH]/[SYNTH]/[NOTE]/[OPEN])
- strips hidden per-paragraph anchors (HTML comments)
- renames the anchor list section to "References"
- removes internal "(keywords: ...)" hints from reference bullets

No transcripts are read or emitted.
"""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHAPTERS_DIR = ROOT / "manuscript" / "chapters"
OUT_DIR = ROOT / "content" / "series" / "chapters"


TAG_RX = re.compile(r"^\[(BACH|SYNTH|NOTE|OPEN)\]\s*", re.IGNORECASE)
SRC_COMMENT_RX = re.compile(r"\s*<!--\s*src:\s*[^>]+-->\s*$", re.IGNORECASE)
CH_TITLE_RX = re.compile(r"^#\s+Chapter\s+\d+:\s*(.+?)\s*$", re.IGNORECASE)
ANCHOR_HEADING = "## Anchors (sources + timecodes)"
ANCHOR_HEADING_OUT = "## References"
ANCHOR_KEYWORDS_RX = re.compile(r"^(\s*-\s+[^\s]+\s+@\s+\d{2}:\d{2}:\d{2})\s+\(keywords:.*\)\s*$", re.IGNORECASE)


def chapter_title(text: str, fallback: str) -> str:
    for line in text.splitlines():
        m = CH_TITLE_RX.match(line.strip())
        if m:
            return m.group(1).strip()
    return fallback


def transform(text: str) -> str:
    out_lines: list[str] = []
    for raw in text.splitlines():
        line = raw.rstrip("\n")

        # Rewrite headings.
        if line.strip() == ANCHOR_HEADING:
            out_lines.append(ANCHOR_HEADING_OUT)
            continue

        # Drop hidden anchor comments.
        line = SRC_COMMENT_RX.sub("", line)

        # Strip internal tags.
        line = TAG_RX.sub("", line)

        # Strip "(keywords: ...)" from anchor bullets.
        m = ANCHOR_KEYWORDS_RX.match(line)
        if m:
            line = m.group(1)

        # Avoid leaving an empty line that used to only carry a tag/comment.
        if not line.strip():
            out_lines.append("")
            continue

        out_lines.append(line)

    # Normalize multiple blank lines (keep at most one).
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
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    chapters = sorted(CHAPTERS_DIR.glob("ch*.md"))
    if not chapters:
        raise SystemExit(f"no chapters found under {CHAPTERS_DIR}")

    index_lines = ["# Chapter Series", "", "Standalone exports of the manuscript chapters.", ""]

    for ch in chapters:
        src = ch.read_text(encoding="utf-8", errors="replace")
        title = chapter_title(src, ch.stem)

        body = transform(src)

        # Rewrite the top-level heading to match blog style.
        lines = body.splitlines()
        if lines and lines[0].startswith("# "):
            lines[0] = f"# {title}"
        else:
            lines.insert(0, f"# {title}")
            lines.insert(1, "")
        body = "\n".join(lines).rstrip() + "\n"

        out_path = OUT_DIR / f"{ch.stem}.md"
        out_path.write_text(body, encoding="utf-8")

        index_lines.append(f"- {title} (`{out_path.relative_to(ROOT)}`)")

    (OUT_DIR / "index.md").write_text("\n".join(index_lines).rstrip() + "\n", encoding="utf-8")
    print(f"wrote {len(chapters)} posts to {OUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
