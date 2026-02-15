#!/usr/bin/env python3
"""
Build a single Markdown file from the chapter files plus references.

This is convenience for reading/export later. It does not change content.
"""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHAPTERS_DIR = ROOT / "manuscript" / "chapters"
REFS_MD = ROOT / "manuscript" / "references.md"
OUT_MD = ROOT / "manuscript" / "book.md"


def main() -> int:
    chapters = sorted(CHAPTERS_DIR.glob("ch*.md"))
    parts = []
    parts.append("# the-mind\n")
    parts.append("A book-length synthesis of how the mind works according to Joscha Bach.\n")
    parts.append("---\n")

    for path in chapters:
        parts.append(path.read_text(encoding="utf-8", errors="replace").rstrip() + "\n")
        parts.append("---\n")

    if REFS_MD.exists():
        parts.append(REFS_MD.read_text(encoding="utf-8", errors="replace").rstrip() + "\n")

    OUT_MD.write_text("\n".join(parts).strip() + "\n", encoding="utf-8")
    print(f"wrote {OUT_MD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

