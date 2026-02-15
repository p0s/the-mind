#!/usr/bin/env python3
"""
One-command build for the public-facing outputs.

This is intentionally simple and local:
- no transcripts are emitted
- outputs go to manuscript/, content/blog/posts/, content/series/chapters/, and dist/ (dist is gitignored)
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable


def run(*args: str) -> None:
    subprocess.run([PY, *args], cwd=str(ROOT), check=True)


def main() -> int:
    run("scripts/build_readme.py")
    run("scripts/add_bach_anchors.py")
    run("scripts/build_references.py")
    run("scripts/build_book_md.py")
    run("scripts/build_book_public_md.py")
    run("scripts/export_blog_posts.py")
    run("scripts/build_site.py", "--out", "dist")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
