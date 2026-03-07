#!/usr/bin/env python3
"""
Import a Substack publication archive into sources/sources.csv.

This uses Substack's public archive API:
  https://<subdomain>.substack.com/api/v1/archive?sort=new&offset=0&limit=50

We keep the canonical sources.csv schema:
  source_id,title,kind,creator_or_channel,url,published_date,language,notes
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from _core.sources import source_id_for_url


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


DEFAULT_CREATORS = {
    "cimcai": "CIMC",
    "joscha": "Joscha Bach",
}


USER_AGENT = "Mozilla/5.0 (the-mind-source-importer/0.1)"


def ymd_from_isoish(s: str) -> str:
    m = re.search(r"(\d{4}-\d{2}-\d{2})", str(s or ""))
    return m.group(1) if m else ""


def norm_title(s: str) -> str:
    return " ".join((s or "").split()).strip()


def fetch_json(url: str) -> object:
    req = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(req, timeout=60) as resp:
        raw = resp.read()
    return json.loads(raw.decode("utf-8", errors="replace") or "null")


@dataclass(frozen=True)
class PostRow:
    url: str
    title: str
    published_date: str


def parse_archive_base(archive_url: str) -> Tuple[str, str]:
    """
    Returns (base_url, pub_key).

    base_url: "https://<host>"
    pub_key: subdomain-like identifier used for discovered_via and default creator mapping
    """
    u = (archive_url or "").strip()
    if not u:
        raise ValueError("empty archive url")
    if not u.startswith(("http://", "https://")):
        u = "https://" + u
    p = urlparse(u)
    host = (p.hostname or "").strip().lower()
    if not host:
        raise ValueError(f"bad archive url: {archive_url!r}")

    base = f"{p.scheme or 'https'}://{host}"

    pub_key = host.split(".", 1)[0]
    return base, pub_key


def iter_archive_posts(base_url: str, *, limit: int = 50) -> List[PostRow]:
    out: List[PostRow] = []
    offset = 0
    while True:
        api = f"{base_url}/api/v1/archive?sort=new&offset={offset}&limit={limit}"
        data = fetch_json(api)
        if not isinstance(data, list) or not data:
            break
        for item in data:
            if not isinstance(item, dict):
                continue
            url = (item.get("canonical_url") or "").strip()
            if not url.startswith(("http://", "https://")):
                continue
            title = norm_title(item.get("title") or "")
            published = ymd_from_isoish(item.get("post_date") or "")
            out.append(PostRow(url=url, title=title, published_date=published))
        offset += len(data)
    return out


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
            out = {k: (r.get(k) or "") for k in CSV_FIELDS}
            writer.writerow(out)


def upsert_posts(
    existing_rows: List[Dict[str, str]],
    existing_by_id: Dict[str, Dict[str, str]],
    posts: List[PostRow],
    *,
    kind: str,
    creator: str,
    notes_suffix: str,
) -> List[Dict[str, str]]:
    new_rows = list(existing_rows)
    for p in posts:
        sid = source_id_for_url(p.url)
        row = existing_by_id.get(sid)
        if row is None:
            row = {
                "source_id": sid,
                "title": p.title,
                "kind": kind,
                "creator_or_channel": creator,
                "url": p.url,
                "published_date": p.published_date,
                "language": "",
                "notes": notes_suffix,
            }
            new_rows.append(row)
            existing_by_id[sid] = row
            continue

        # Update missing fields only.
        if not row.get("title") and p.title:
            row["title"] = p.title
        if not row.get("kind") and kind:
            row["kind"] = kind
        if not row.get("creator_or_channel") and creator:
            row["creator_or_channel"] = creator
        if not row.get("url"):
            row["url"] = p.url
        if not row.get("published_date") and p.published_date:
            row["published_date"] = p.published_date

    # Deterministic ordering: date desc, then source_id.
    def sort_key(r: Dict[str, str]) -> Tuple[str, str]:
        d = r.get("published_date") or ""
        return ("" if d else "1") + d, r.get("source_id") or ""

    new_rows.sort(key=sort_key)
    new_rows.reverse()
    return new_rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--archive", required=True, help="Substack archive URL (e.g., https://cimcai.substack.com/archive)")
    ap.add_argument("--csv", default="sources/sources.csv", help="canonical sources CSV")
    ap.add_argument("--kind", default="web", help="kind for these rows (default: web)")
    ap.add_argument("--creator", default="", help="creator/channel label (default: inferred from subdomain)")
    ap.add_argument("--notes", default="", help="notes string to attach to newly-added rows (default: inferred)")
    args = ap.parse_args()

    base_url, pub_key = parse_archive_base(args.archive)
    creator = (args.creator or DEFAULT_CREATORS.get(pub_key, "")).strip()

    notes_suffix = (args.notes or "").strip()
    if not notes_suffix:
        notes_suffix = f"curation_status=candidate tier=aux priority=3 discovered_via=substack_archive:{pub_key} format=essay"

    posts = iter_archive_posts(base_url)

    csv_path = Path(args.csv)
    existing_rows, existing_by_id = read_sources_csv(csv_path)
    merged = upsert_posts(existing_rows, existing_by_id, posts, kind=args.kind, creator=creator, notes_suffix=notes_suffix)
    write_sources_csv(csv_path, merged)

    print(f"Imported {len(posts)} Substack posts ({pub_key}) -> {csv_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
