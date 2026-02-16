#!/usr/bin/env python3
"""
Print a prioritized "next work" queue for sources in sources/sources.csv.

This is intentionally lightweight:
- sources/sources.csv is the source of truth (committed)
- transcripts/_index.csv is optional (local-only; gitignored)
- sources/source_notes/ presence is used to detect whether a source has been extracted into notes yet (committed)
"""

from __future__ import annotations

import argparse
import csv
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


ROOT = Path(__file__).resolve().parents[1]
SOURCES_CSV = ROOT / "sources" / "sources.csv"
INDEX_CSV = ROOT / "transcripts" / "_index.csv"
SOURCE_NOTES_DIR = ROOT / "sources" / "source_notes"


CURATION_RANK = {"keep": 0, "candidate": 1, "reject": 2, "": 9}
TIER_RANK = {"keystone": 0, "supporting": 1, "legacy": 2, "aux": 3, "": 9}
TRANSCRIPT_RANK = {"ok": 0, "needs_asr": 1, "unavailable": 2, "error": 3, "": 9}


@dataclass(frozen=True)
class Entry:
    source_id: str
    title: str
    kind: str
    url: str
    published_date: str
    curation_status: str
    tier: str
    fmt: str
    priority: int
    transcript_status: str
    note_exists: bool


def eprint(*args: object) -> None:
    print(*args, file=sys.stderr)


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


def parse_int(v: str, default: int) -> int:
    try:
        return int((v or "").strip())
    except Exception:
        return default


def date_key(s: str) -> int:
    # Expected YYYY-MM-DD; fallback 0.
    t = (s or "").strip()
    if len(t) != 10 or t[4] != "-" or t[7] != "-":
        return 0
    try:
        return int(t.replace("-", ""))
    except Exception:
        return 0


def load_transcript_statuses(index_path: Path) -> Dict[str, str]:
    if not index_path.exists():
        return {}
    out: Dict[str, str] = {}
    with index_path.open("r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            sid = (row.get("source_id") or "").strip()
            if not sid:
                continue
            out[sid] = (row.get("status") or "").strip()
    return out


def iter_sources(path: Path) -> Iterable[dict]:
    with path.open("r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            yield row


def note_exists(notes_dir: Path, source_id: str) -> bool:
    return (notes_dir / f"{source_id}.md").exists()


def build_entries(
    *,
    sources_csv: Path,
    index_csv: Path,
    notes_dir: Path,
    include_reject: bool,
    curation_filter: Sequence[str],
    tier_filter: Sequence[str],
    kind_filter: Sequence[str],
    missing_notes_only: bool,
) -> List[Entry]:
    transcript_status_by_id = load_transcript_statuses(index_csv)

    out: List[Entry] = []
    for row in iter_sources(sources_csv):
        sid = (row.get("source_id") or "").strip()
        if not sid:
            continue
        title = " ".join((row.get("title") or "").split())
        kind = (row.get("kind") or "").strip()
        url = (row.get("url") or "").strip()
        published_date = (row.get("published_date") or "").strip()

        kv = parse_notes_kv(row.get("notes") or "")
        curation_status = (kv.get("curation_status") or "").strip()
        tier = (kv.get("tier") or "").strip()
        fmt = (kv.get("format") or "").strip()
        priority = parse_int(kv.get("priority", ""), default=99)

        if not include_reject and curation_status == "reject":
            continue
        if curation_filter and curation_status not in curation_filter:
            continue
        if tier_filter and tier not in tier_filter:
            continue
        if kind_filter and kind not in kind_filter:
            continue

        has_note = note_exists(notes_dir, sid)
        if missing_notes_only and has_note:
            continue

        tr_status = transcript_status_by_id.get(sid, "").strip()
        out.append(
            Entry(
                source_id=sid,
                title=title,
                kind=kind,
                url=url,
                published_date=published_date,
                curation_status=curation_status,
                tier=tier,
                fmt=fmt,
                priority=priority,
                transcript_status=tr_status,
                note_exists=has_note,
            )
        )

    return out


def sort_key(e: Entry) -> Tuple[int, int, int, int, int, int, str]:
    return (
        e.priority,
        CURATION_RANK.get(e.curation_status, 9),
        TIER_RANK.get(e.tier, 9),
        0 if not e.note_exists else 1,
        TRANSCRIPT_RANK.get(e.transcript_status, 9),
        -date_key(e.published_date),
        e.source_id,
    )


def render_tsv(entries: List[Entry]) -> str:
    rows = [
        [
            "priority",
            "curation_status",
            "tier",
            "transcript_status",
            "note",
            "format",
            "source_id",
            "published_date",
            "kind",
            "title",
            "url",
        ]
    ]
    for e in entries:
        rows.append(
            [
                str(e.priority),
                e.curation_status,
                e.tier,
                e.transcript_status,
                "yes" if e.note_exists else "no",
                e.fmt,
                e.source_id,
                e.published_date,
                e.kind,
                e.title,
                e.url,
            ]
        )
    return "\n".join(["\t".join(r) for r in rows]).rstrip() + "\n"


def render_markdown(entries: List[Entry]) -> str:
    headers = ["prio", "curation", "tier", "tr", "note", "fmt", "source_id", "date", "title"]
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
    for e in entries:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(e.priority),
                    e.curation_status or "",
                    e.tier or "",
                    e.transcript_status or "",
                    "✓" if e.note_exists else "",
                    e.fmt or "",
                    f"`{e.source_id}`",
                    e.published_date or "",
                    (e.title or e.source_id).replace("|", "\\|"),
                ]
            )
            + " |"
        )
    return "\n".join(lines).rstrip() + "\n"


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sources", default=str(SOURCES_CSV), help="Path to sources/sources.csv")
    ap.add_argument("--index", default=str(INDEX_CSV), help="Path to transcripts/_index.csv (optional; local-only)")
    ap.add_argument("--notes-dir", default=str(SOURCE_NOTES_DIR), help="Path to sources/source_notes/")
    ap.add_argument("--limit", type=int, default=60, help="Maximum rows to print")
    ap.add_argument("--output", choices=["tsv", "markdown"], default="tsv", help="Output format")
    ap.add_argument("--include-reject", action="store_true", help="Include sources tagged curation_status=reject")
    ap.add_argument("--curation", default="", help="Comma-separated curation_status filter (keep,candidate,reject)")
    ap.add_argument("--tier", default="", help="Comma-separated tier filter (keystone,supporting,legacy,aux)")
    ap.add_argument("--kind", default="", help="Comma-separated kind filter (youtube,ccc,web,...)")
    ap.add_argument("--missing-notes", action="store_true", help="Only show sources missing sources/source_notes/<id>.md")
    args = ap.parse_args(list(argv) if argv is not None else None)

    sources_csv = Path(args.sources)
    index_csv = Path(args.index)
    notes_dir = Path(args.notes_dir)

    if not sources_csv.exists():
        eprint(f"missing sources.csv: {sources_csv}")
        return 2

    curation_filter = [s.strip() for s in args.curation.split(",") if s.strip()]
    tier_filter = [s.strip() for s in args.tier.split(",") if s.strip()]
    kind_filter = [s.strip() for s in args.kind.split(",") if s.strip()]

    entries = build_entries(
        sources_csv=sources_csv,
        index_csv=index_csv,
        notes_dir=notes_dir,
        include_reject=bool(args.include_reject),
        curation_filter=curation_filter,
        tier_filter=tier_filter,
        kind_filter=kind_filter,
        missing_notes_only=bool(args.missing_notes),
    )
    entries.sort(key=sort_key)
    entries = entries[: max(0, int(args.limit))]

    if args.output == "markdown":
        sys.stdout.write(render_markdown(entries))
    else:
        sys.stdout.write(render_tsv(entries))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
