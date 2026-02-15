#!/usr/bin/env python3
"""
Quick progress snapshot for the project (safe to run; no network).
"""

from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCES_CSV = ROOT / "sources" / "sources.csv"
INDEX_CSV = ROOT / "transcripts" / "_index.csv"
SPEAKERS_DIR = ROOT / "transcripts" / "_speakers"
CLAIMS_MD = ROOT / "notes" / "claims.md"
GLOSSARY_MD = ROOT / "notes" / "glossary.md"
CHAPTERS_DIR = ROOT / "manuscript" / "chapters"


def count_words(path: Path) -> int:
    txt = path.read_text(encoding="utf-8", errors="replace")
    return len(txt.split())


def main() -> int:
    # sources.csv
    status_c = Counter()
    tier_c = Counter()
    kind_c = Counter()
    total_sources = 0
    with SOURCES_CSV.open("r", encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            total_sources += 1
            kind_c[r.get("kind", "")] += 1
            notes = r.get("notes", "") or ""
            status = ""
            tier = ""
            for tok in notes.split():
                if tok.startswith("curation_status=") and not status:
                    status = tok.split("=", 1)[1]
                if tok.startswith("tier=") and not tier:
                    tier = tok.split("=", 1)[1]
            status_c[status or ""] += 1
            tier_c[tier or ""] += 1

    # transcripts index
    tr_status = Counter()
    total_index = 0
    if INDEX_CSV.exists():
        with INDEX_CSV.open("r", encoding="utf-8", newline="") as f:
            for r in csv.DictReader(f):
                total_index += 1
                tr_status[r.get("status", "")] += 1

    # speaker files
    speaker_files = sorted(p for p in SPEAKERS_DIR.glob("*.speakers.json")) if SPEAKERS_DIR.exists() else []

    # claims/glossary counts
    claims = sum(1 for line in CLAIMS_MD.read_text(encoding="utf-8", errors="replace").splitlines() if line.startswith("## CLM-"))
    terms = sum(1 for line in GLOSSARY_MD.read_text(encoding="utf-8", errors="replace").splitlines() if line.startswith("## "))

    # manuscript words
    chapter_paths = sorted(CHAPTERS_DIR.glob("ch*.md"))
    chapter_words = sum(count_words(p) for p in chapter_paths)

    print("sources.csv")
    print(f"  total: {total_sources}")
    print(f"  kinds: {dict(kind_c)}")
    print(f"  curation_status: {dict(status_c)}")
    print(f"  tier: {dict(tier_c)}")
    print("")

    print("transcripts/_index.csv (local)")
    print(f"  rows: {total_index}")
    print(f"  status: {dict(tr_status)}")
    print("")

    print("speaker attribution (local)")
    print(f"  speaker files: {len(speaker_files)}")
    print("")

    print("knowledge base")
    print(f"  claims: {claims}")
    print(f"  glossary terms: {terms}")
    print("")

    print("manuscript")
    print(f"  chapters: {len(chapter_paths)}")
    print(f"  words (chapters): {chapter_words}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

