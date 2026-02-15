#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import re
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional, Tuple


ROOT = Path(__file__).resolve().parents[1]
SOURCES_CSV = ROOT / "sources" / "sources.csv"

ALLOWED_PRESENTATION_FORMATS = {"talk", "interview", "essay"}

_ESSAY_HINTS = (
    "summary",
    "summaries",
    "overview",
    "explained",
    "analysis",
    "breakdown",
    "debunked",
    "notebooklm",
    "notebook lm",
    "database",
    "tmp upload",
    "reaction",
    "commentary",
    "erklärt",
    "erklaert",
    "ai summary",
)

_INTERVIEW_CREATOR_EXACT = {
    # Primary interview/podcast channels we use a lot.
    "Lex Fridman",
    "Lex Clips",
    "Lex Fridman Clips",
    "Machine Learning Street Talk",
    "Curt Jaimungal",
    "Audience of One",
    "Jim Rutt Show",
    "The Neha Anwar Podcast",
    "Vance Crowe",
    "Theory of EveryOne with Tyler Goldstein",
    "Neural Echo Chronicles",
}

_INTERVIEW_CREATOR_SUBSTR = (
    "podcast",
    "show",
    "cast",
    "energiegespräch",
    "energiegespraech",
)

_INTERVIEW_HINTS = (
    "interview",
    "podcast",
    "conversation",
    "salon",
    "debate",
    "q&a",
    "qa",
    "im gespräch",
    "im gespraech",
    "gespräch",
    "gespraech",
    "lex fridman",
    "curt jaimungal",
    "street talk",
)

_TALK_HINTS = (
    "talk",
    "lecture",
    "keynote",
    "presentation",
    "summit",
    "conference",
    "workshop",
    "seminar",
    "colloquium",
    "vortrag",
)

_EP_RX = re.compile(r"\b(?:ep\.?\s*\d+|episode\s*\d+|ep\d+)\b", re.IGNORECASE)
_HASHNUM_RX = re.compile(r"#\d{1,4}\b")


def parse_notes_kv(notes: str) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for tok in (notes or "").split():
        if "=" not in tok:
            continue
        k, v = tok.split("=", 1)
        k = k.strip()
        v = v.strip()
        if k and v:
            out[k] = v
    return out


def normalize_presentation_format(v: str) -> Optional[str]:
    x = (v or "").strip().lower()
    if not x:
        return None
    if x in ALLOWED_PRESENTATION_FORMATS:
        return x

    if x in {"podcast", "conversation", "qa"}:
        return "interview"
    if x in {"lecture", "presentation", "keynote"}:
        return "talk"
    if x in {"article", "post", "blog"}:
        return "essay"

    # "video"/"clip"/etc are media types, not presentation types; do not preserve.
    return None


def infer_presentation_format(meta: Dict[str, str], *, force: bool) -> str:
    notes = meta.get("notes") or ""
    kv = parse_notes_kv(notes)
    if not force:
        fmt = normalize_presentation_format(kv.get("format") or "")
        if fmt:
            return fmt

    kind = (meta.get("kind") or "").strip().lower()
    url = (meta.get("url") or "").strip().lower()
    title = (meta.get("title") or "").strip().lower()
    creator = (meta.get("creator_or_channel") or "").strip().lower()
    hay = " ".join([title, creator])

    if kind in {"web"}:
        return "essay"

    if "media.ccc.de" in url or kind in {"ccc"}:
        return "talk"

    # YouTube (and other video sources): first detect essay-like secondary material (summaries, analysis, commentary).
    if any(w in hay for w in _ESSAY_HINTS):
        return "essay"

    if meta.get("creator_or_channel") in _INTERVIEW_CREATOR_EXACT:
        return "interview"
    if any(w in creator for w in _INTERVIEW_CREATOR_SUBSTR):
        return "interview"

    if any(w in hay for w in _INTERVIEW_HINTS):
        return "interview"

    # Episode numbering is a strong interview/podcast signal (unless it explicitly looks like a talk).
    if (_EP_RX.search(title) or _HASHNUM_RX.search(title)) and not any(w in hay for w in _TALK_HINTS):
        return "interview"

    if any(w in hay for w in _TALK_HINTS):
        return "talk"

    return "talk"


def split_line_ending(line: str) -> Tuple[str, str]:
    if line.endswith("\r\n"):
        return line[:-2], "\r\n"
    if line.endswith("\n"):
        return line[:-1], "\n"
    return line, ""


def upsert_format_token(notes: str, fmt: str) -> str:
    toks = [t for t in (notes or "").split() if t and not t.lower().startswith("format=")]
    toks.append(f"format={fmt}")
    return " ".join(toks).strip()


def normalize_file(path: Path, *, force: bool) -> None:
    raw = path.read_bytes().decode("utf-8", errors="replace")
    lines = raw.splitlines(keepends=True)
    if not lines:
        raise SystemExit(f"empty file: {path}")

    header_body, header_end = split_line_ending(lines[0])
    header = next(csv.reader([header_body]))

    expected = ["source_id", "title", "kind", "creator_or_channel", "url", "published_date", "language", "notes"]
    if header != expected:
        raise SystemExit(f"unexpected header in {path}: {header}")

    fmt_counts: Counter[str] = Counter()
    changed = 0
    out_lines: List[str] = [header_body + header_end]

    for line in lines[1:]:
        body, end = split_line_ending(line)
        if not body.strip():
            out_lines.append(body + end)
            continue

        row_fields = next(csv.reader([body]))
        if len(row_fields) != len(header):
            raise SystemExit(f"bad row (expected {len(header)} cols, got {len(row_fields)}): {body[:200]}")

        row = dict(zip(header, row_fields))
        fmt = infer_presentation_format(row, force=force)
        fmt_counts[fmt] += 1

        old_notes = row.get("notes") or ""
        new_notes = upsert_format_token(old_notes, fmt)

        if new_notes != old_notes:
            prefix, _old_tail = body.rsplit(",", 1)
            body = prefix + "," + new_notes
            changed += 1

        out_lines.append(body + end)

    path.write_text("".join(out_lines), encoding="utf-8")

    print(f"updated {path}")
    print(f"rows changed: {changed}")
    for k in ("talk", "interview", "essay"):
        print(f"{k}: {fmt_counts[k]}")


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="Recompute and overwrite existing format= tokens.")
    args = ap.parse_args(argv)

    normalize_file(SOURCES_CSV, force=args.force)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
