#!/usr/bin/env python3
"""
Import a list of web URLs into sources/sources.csv.

This is a lightweight helper for non-YouTube, non-CCC sources (articles, essays,
podcast show notes, etc.).

It attempts to extract:
  - title: og:title, then <title>
  - published_date: article:published_time, then datePublished meta/time tags

Usage:
  python3 scripts/import_web_urls.py --urls sources/url_lists/singularityweblog.txt \\
    --creator 'Singularity Weblog' --notes 'discovered_via=manual list'
"""

from __future__ import annotations

import argparse
import csv
import html
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse
from urllib.request import Request, urlopen


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

USER_AGENT = "the-mind-source-importer/0.1 (+https://github.com/p0s/the-mind)"


def fetch_text(url: str) -> str:
    req = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(req, timeout=60) as resp:
        raw = resp.read()
    return raw.decode("utf-8", errors="replace")


def sanitize_id_component(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    return s.strip("_")


def ymd_from_isoish(s: str) -> str:
    m = re.search(r"(\d{4}-\d{2}-\d{2})", s or "")
    return m.group(1) if m else ""


def extract_meta(html_text: str, property_name: str) -> str:
    m = re.search(
        rf'<meta[^>]+property="{re.escape(property_name)}"[^>]+content="([^"]+)"',
        html_text,
        flags=re.IGNORECASE,
    )
    if m:
        return html.unescape(m.group(1)).strip()
    m = re.search(
        rf'<meta[^>]+content="([^"]+)"[^>]+property="{re.escape(property_name)}"',
        html_text,
        flags=re.IGNORECASE,
    )
    if m:
        return html.unescape(m.group(1)).strip()
    return ""


def extract_title(html_text: str) -> str:
    title = extract_meta(html_text, "og:title")
    if title:
        return title
    m = re.search(r"<title>\s*(.*?)\s*</title>", html_text, flags=re.DOTALL | re.IGNORECASE)
    if not m:
        return ""
    return html.unescape(m.group(1)).strip()


def extract_published_date(html_text: str) -> str:
    # Common meta tags
    for prop in ("article:published_time", "og:updated_time"):
        v = extract_meta(html_text, prop)
        d = ymd_from_isoish(v)
        if d:
            return d

    # Microdata: <meta itemprop="datePublished" content="YYYY-MM-DD" />
    m = re.search(
        r'itemprop="datePublished"[^>]+content="([^"]+)"', html_text, flags=re.IGNORECASE
    )
    if m:
        d = ymd_from_isoish(m.group(1))
        if d:
            return d

    # <time datetime="YYYY-MM-DD...">
    m = re.search(r"<time[^>]+datetime=\"([^\"]+)\"", html_text, flags=re.IGNORECASE)
    if m:
        d = ymd_from_isoish(m.group(1))
        if d:
            return d

    return ""


def source_id_for_url(url: str) -> str:
    p = urlparse(url)
    host = sanitize_id_component((p.hostname or "web").replace("www.", ""))
    path = sanitize_id_component(p.path.strip("/")) or "root"
    return f"web_{host}_{path}"


@dataclass(frozen=True)
class WebRow:
    url: str
    title: str
    published_date: str


def read_urls_file(path: Path) -> List[str]:
    out: List[str] = []
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        s = raw.strip()
        if not s or s.startswith("#"):
            continue
        out.append(s)
    return out


def read_sources_csv(path: Path) -> Tuple[List[Dict[str, str]], Dict[str, Dict[str, str]]]:
    if not path.exists():
        return [], {}
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

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


def upsert_web_rows(
    existing_rows: List[Dict[str, str]],
    existing_by_id: Dict[str, Dict[str, str]],
    web_rows: List[WebRow],
    kind: str,
    creator: str,
    notes_suffix: str,
) -> List[Dict[str, str]]:
    new_rows = list(existing_rows)
    for w in web_rows:
        sid = source_id_for_url(w.url)
        row = existing_by_id.get(sid)
        if row is None:
            row = {
                "source_id": sid,
                "title": w.title,
                "kind": kind,
                "creator_or_channel": creator,
                "url": w.url,
                "published_date": w.published_date,
                "language": "",
                "notes": notes_suffix,
            }
            new_rows.append(row)
            existing_by_id[sid] = row
            continue

        if not row.get("title") and w.title:
            row["title"] = w.title
        if not row.get("kind") and kind:
            row["kind"] = kind
        if not row.get("creator_or_channel") and creator:
            row["creator_or_channel"] = creator
        if not row.get("url"):
            row["url"] = w.url
        if not row.get("published_date") and w.published_date:
            row["published_date"] = w.published_date

    def sort_key(r: Dict[str, str]) -> Tuple[str, str]:
        d = r.get("published_date") or ""
        return ("" if d else "1") + d, r.get("source_id") or ""

    new_rows.sort(key=sort_key)
    new_rows.reverse()
    return new_rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--urls", required=True, help="text file with one URL per line")
    ap.add_argument("--csv", default="sources/sources.csv", help="canonical sources CSV")
    ap.add_argument("--kind", default="web", help="kind for these rows (default: web)")
    ap.add_argument("--creator", default="", help="creator/channel/publisher label")
    ap.add_argument("--notes", default="", help="notes string to attach to newly-added rows")
    args = ap.parse_args()

    urls = read_urls_file(Path(args.urls))
    rows: List[WebRow] = []
    for u in urls:
        try:
            page_html = fetch_text(u)
        except Exception:
            rows.append(WebRow(url=u, title="", published_date=""))
            continue
        rows.append(
            WebRow(
                url=u,
                title=extract_title(page_html),
                published_date=extract_published_date(page_html),
            )
        )

    csv_path = Path(args.csv)
    existing_rows, existing_by_id = read_sources_csv(csv_path)
    merged = upsert_web_rows(existing_rows, existing_by_id, rows, args.kind, args.creator, args.notes)
    write_sources_csv(csv_path, merged)

    print(f"Imported {len(rows)} web URLs -> {csv_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
