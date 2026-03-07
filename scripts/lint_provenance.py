#!/usr/bin/env python3
"""
Lint provenance / citation syntax (Option 1).

Contract:
- Prose citations are hidden HTML comments at end of line:
    <!-- src: <source_id> @ <locator>; <source_id> @ <locator> | auto=... -->
- List citations are visible and start the list item:
    - <source_id> @ <locator> ...
- In manuscript chapters, the "Anchors (sources + timecodes)" section requires
  "(keywords: ...)" tails for anchor bullets (used by scripts/add_bach_anchors.py).

This is intentionally conservative: it only validates the two canonical
encodings and rejects ad-hoc variants.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

from _core.provenance import find_src_comments, parse_src_comment_eol
from _core.sources import load_source_ids as core_load_source_ids
from _core.locators import normalize_locator, valid_locator


ROOT = Path(__file__).resolve().parents[1]
SOURCES_CSV = ROOT / "sources" / "sources.csv"

CHAPTERS = sorted((ROOT / "manuscript" / "chapters").glob("ch*.md"))
BLOG_INDEX = ROOT / "content" / "blog" / "index.md"
BLOG_POSTS = sorted((ROOT / "content" / "blog" / "posts").glob("*.md"))
NOTES = [
    ROOT / "notes" / "glossary.md",
    ROOT / "notes" / "claims.md",
    ROOT / "notes" / "lineage.md",
]
HOME = ROOT / "site" / "home.md"


LIST_CITE_RX = re.compile(
    r"^\s*(?:-|\*|\+|\d+\.)\s+([a-z0-9_\-]+)\s+@\s*([^\s)]+)\b",
    re.IGNORECASE,
)

# Any visible "source_id @ timecode" token (used to catch stray prose citations).
VISIBLE_CITE_TOKEN_RX = re.compile(
    r"\b([a-z0-9_\-]+)\s+@\s*([^\s)]+)\b",
    re.IGNORECASE,
)

CHAPTER_ANCHOR_HEADING = "## Anchors (sources + timecodes)"
CHAPTER_ANCHOR_ITEM_RX = re.compile(
    r"^\s*-\s+([a-z0-9_\-]+)\s+@\s*([^\s]+)\s+\(keywords:\s*.+\)\s*$",
    re.IGNORECASE,
)

BACH_TAG_LINE_RX = re.compile(r"^\[BACH\]\b", re.IGNORECASE)


@dataclass(frozen=True)
class LintError:
    path: Path
    line_no: int
    message: str
    line: str


def load_source_ids() -> Set[str]:
    if not SOURCES_CSV.exists():
        raise SystemExit(f"missing {SOURCES_CSV}")
    return core_load_source_ids(SOURCES_CSV)


def iter_target_files() -> List[Path]:
    files: List[Path] = []
    files.extend([p for p in [HOME, BLOG_INDEX, *NOTES] if p.exists()])
    files.extend([p for p in CHAPTERS if p.exists()])
    files.extend([p for p in BLOG_POSTS if p.exists()])
    return files


def lint_file(path: Path, *, source_ids: Set[str]) -> List[LintError]:
    errors: List[LintError] = []
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()

    in_chapter_anchors = False
    is_chapter = path.parts[-3:-1] == ("manuscript", "chapters") or (
        "manuscript" in path.parts and "chapters" in path.parts
    )

    for i, raw in enumerate(lines, start=1):
        line = raw.rstrip("\n")

        if is_chapter:
            if line.strip() == CHAPTER_ANCHOR_HEADING:
                in_chapter_anchors = True
            elif in_chapter_anchors and line.startswith("## ") and line.strip() != CHAPTER_ANCHOR_HEADING:
                in_chapter_anchors = False

        # Disallow src comments inside list item lines (use list cite syntax instead).
        if find_src_comments(line) and re.match(r"^\s*(?:-|\*|\+|\d+\.)\s+", line):
            errors.append(
                LintError(
                    path,
                    i,
                    "Do not use <!-- src: ... --> inside list items; use '- <source_id> @ <locator>' instead.",
                    line,
                )
            )

        # Validate canonical src comments (must be end-of-line, must reference known source_id).
        comments = find_src_comments(line)
        if comments:
            parsed = parse_src_comment_eol(line)
            if not parsed:
                errors.append(
                    LintError(
                        path,
                        i,
                        "Non-canonical src comment; must be '... <!-- src: <source_id> @ <locator>; ... -->' at end of line.",
                        line,
                    )
                )
            else:
                for sid, tc in parsed.refs:
                    if sid not in source_ids:
                        errors.append(LintError(path, i, f"Unknown source_id '{sid}' (not in sources/sources.csv).", line))
                    loc = normalize_locator(tc)
                    if not valid_locator(loc):
                        errors.append(LintError(path, i, f"Invalid locator '{tc}' (expected HH:MM:SS[.mmm] or pN[-M]).", line))

                meta = parsed.meta_dict
                if meta.get("auto", "").strip().lower() == "needs_review":
                    errors.append(LintError(path, i, "Found auto=needs_review anchor; must be resolved manually.", line))

                # Ensure there's only one src comment on the line.
                if len(comments) > 1:
                    errors.append(LintError(path, i, "Multiple src comments on one line; use exactly one.", line))

        # Validate list citation items (visible form).
        m_list = LIST_CITE_RX.match(line)
        if m_list:
            sid, tc = m_list.group(1), m_list.group(2)
            if sid not in source_ids:
                errors.append(LintError(path, i, f"Unknown source_id '{sid}' (not in sources/sources.csv).", line))
            loc = normalize_locator(tc)
            if not valid_locator(loc):
                errors.append(LintError(path, i, f"Invalid locator '{tc}' (expected HH:MM:SS[.mmm] or pN[-M]).", line))

        # Enforce chapter anchors list format (keywords tail required).
        if in_chapter_anchors and line.lstrip().startswith("- "):
            m_anchor = CHAPTER_ANCHOR_ITEM_RX.match(line)
            if not m_anchor:
                errors.append(
                    LintError(
                        path,
                        i,
                        "Chapter anchor bullets must be '- <source_id> @ <locator> (keywords: ...)' (used by add_bach_anchors.py).",
                        line,
                    )
                )
            else:
                sid, tc = m_anchor.group(1), m_anchor.group(2)
                if sid not in source_ids:
                    errors.append(LintError(path, i, f"Unknown source_id '{sid}' (not in sources/sources.csv).", line))
                loc = normalize_locator(tc)
                if not valid_locator(loc):
                    errors.append(LintError(path, i, f"Invalid locator '{tc}' (expected HH:MM:SS[.mmm] or pN[-M]).", line))

        # Catch stray visible cite tokens in prose (not a list item, not in a src comment).
        # Only flag tokens whose source_id is known.
        without_comments = re.sub(r"<!--\s*src:\s*.*?-->", "", line, flags=re.IGNORECASE)
        if not LIST_CITE_RX.match(without_comments):
            for m_vis in VISIBLE_CITE_TOKEN_RX.finditer(without_comments):
                sid = m_vis.group(1)
                tc = m_vis.group(2)
                if sid not in source_ids:
                    continue
                if valid_locator(normalize_locator(tc)):
                    errors.append(
                        LintError(
                            path,
                            i,
                            "Visible 'source_id @ locator' in prose; use a hidden end-of-line comment instead: <!-- src: ... -->.",
                            line,
                        )
                    )

        # BACH tag lines must include a canonical src comment somewhere on the line.
        # (add_bach_anchors.py enforces this in chapters, but we lint for drift.)
        if BACH_TAG_LINE_RX.match(line):
            if not parse_src_comment_eol(line):
                errors.append(
                    LintError(
                        path,
                        i,
                        "[BACH] lines must include a canonical end-of-line src comment: <!-- src: <source_id> @ <locator>; ... -->.",
                        line,
                    )
                )

    return errors


def main(argv: Sequence[str] | None = None) -> int:
    _ = argv
    source_ids = load_source_ids()
    all_errors: List[LintError] = []
    for p in iter_target_files():
        all_errors.extend(lint_file(p, source_ids=source_ids))

    if not all_errors:
        return 0

    for e in all_errors:
        rel = e.path.relative_to(ROOT) if e.path.is_absolute() else e.path
        print(f"{rel}:{e.line_no}: {e.message}")
        print(f"  {e.line}")
    print(f"\n{len(all_errors)} provenance lint error(s).", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
