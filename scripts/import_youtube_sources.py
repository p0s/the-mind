#!/usr/bin/env python3
"""
Import yt-dlp output into sources/sources.csv.

Expected input format (one line per video), fields separated by literal "\\t":
  id\\tuploader\\tupload_date\\tduration\\ttitle\\twebpage_url

We keep the CSV schema stable:
  source_id,title,kind,creator_or_channel,url,published_date,language,notes
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple


CSV_FIELDS = [
    "source_id",
    "title",
    "kind",
    "creator_or_channel",
    "url",
    "published_date",
    "language",
    "notes",
]


def yyyymmdd_to_iso(s: str) -> str:
    s = (s or "").strip()
    if len(s) != 8 or not s.isdigit():
        return ""
    return f"{s[0:4]}-{s[4:6]}-{s[6:8]}"


@dataclass(frozen=True)
class YtRow:
    video_id: str
    uploader: str
    upload_date: str
    duration: str
    title: str
    url: str


def parse_yt_tsv(path: Path) -> List[YtRow]:
    rows: List[YtRow] = []
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        parts = raw.split("\\t")
        if len(parts) < 6:
            continue
        video_id, uploader, upload_date, duration, title, url = parts[:6]
        video_id = video_id.strip()
        url = url.strip()
        if not video_id or not url.startswith("http"):
            continue
        rows.append(
            YtRow(
                video_id=video_id,
                uploader=uploader.strip(),
                upload_date=upload_date.strip(),
                duration=duration.strip(),
                title=title.strip(),
                url=url,
            )
        )
    return rows


def read_sources_csv(path: Path) -> Tuple[List[Dict[str, str]], Dict[str, Dict[str, str]]]:
    if not path.exists():
        return [], {}
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    # Deduplicate by source_id (merge non-empty fields).
    merged: Dict[str, Dict[str, str]] = {}
    order: List[str] = []
    for r in rows:
        sid = (r.get("source_id") or "").strip()
        if not sid:
            continue
        if sid not in merged:
            merged[sid] = dict(r)
            order.append(sid)
            continue
        cur = merged[sid]
        for k in CSV_FIELDS:
            if not cur.get(k) and r.get(k):
                cur[k] = r[k]

    canonical = [merged[sid] for sid in order]
    return canonical, merged


def write_sources_csv(path: Path, rows: List[Dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for r in rows:
            # Ensure all fields exist to keep output stable.
            out = {k: (r.get(k) or "") for k in CSV_FIELDS}
            writer.writerow(out)


def upsert_youtube_rows(
    existing_rows: List[Dict[str, str]],
    existing_by_id: Dict[str, Dict[str, str]],
    yt_rows: List[YtRow],
    notes_suffix: str,
) -> List[Dict[str, str]]:
    new_rows = list(existing_rows)

    for y in yt_rows:
        sid = f"yt_{y.video_id}"
        published = yyyymmdd_to_iso(y.upload_date)
        row = existing_by_id.get(sid)

        if row is None:
            row = {
                "source_id": sid,
                "title": y.title,
                "kind": "youtube",
                "creator_or_channel": y.uploader,
                "url": y.url,
                "published_date": published,
                "language": "",
                "notes": notes_suffix,
            }
            new_rows.append(row)
            existing_by_id[sid] = row
            continue

        # Update missing fields only (never overwrite a populated field).
        if not row.get("title"):
            row["title"] = y.title
        if not row.get("creator_or_channel"):
            row["creator_or_channel"] = y.uploader
        if not row.get("url"):
            row["url"] = y.url
        if not row.get("published_date") and published:
            row["published_date"] = published
        if not row.get("kind"):
            row["kind"] = "youtube"

    # Re-sort: prefer deterministic ordering (date desc, then source_id).
    def sort_key(r: Dict[str, str]) -> Tuple[str, str]:
        # Empty dates sort last. We invert by sorting on negative via string tricks:
        # YYYY-MM-DD is lexicographically sortable.
        d = r.get("published_date") or ""
        return ("" if d else "1") + d, r.get("source_id") or ""

    # Sort ascending using the prefixed key, then reverse for date-desc.
    new_rows.sort(key=sort_key)
    new_rows.reverse()
    return new_rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tsv", default="/tmp/ytmeta_joscha_bach.tsv", help="yt-dlp TSV file")
    ap.add_argument("--csv", default="sources/sources.csv", help="canonical sources CSV")
    ap.add_argument(
        "--notes",
        default="discovered_via=ytsearch:Joscha Bach",
        help="notes string to attach to newly-added rows",
    )
    args = ap.parse_args()

    tsv_path = Path(args.tsv)
    csv_path = Path(args.csv)
    yt_rows = parse_yt_tsv(tsv_path)
    existing_rows, existing_by_id = read_sources_csv(csv_path)
    merged = upsert_youtube_rows(existing_rows, existing_by_id, yt_rows, args.notes)
    write_sources_csv(csv_path, merged)
    print(f"Imported {len(yt_rows)} youtube rows -> {csv_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
