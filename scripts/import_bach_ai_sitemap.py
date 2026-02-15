#!/usr/bin/env python3
"""
Import Joscha Bach article pages from bach.ai into sources/sources.csv.

Discovery:
  - Fetch sitemap: http://bach.ai/sitemap.xml
  - Extract URLs
  - Skip obvious index/pagination URLs

Filter:
  - Keep only pages that look like "article" pages (og:type=article or
    article:published_time meta tag).

Notes:
  - bach.ai currently serves HTTPS with a certificate hostname mismatch.
    We use HTTP endpoints for fetching.
"""

from __future__ import annotations

import argparse
import csv
import html
import re
import xml.etree.ElementTree as ET
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
SITEMAP_URL = "http://bach.ai/sitemap.xml"


def fetch_text(url: str) -> str:
    req = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(req, timeout=60) as resp:
        raw = resp.read()
    return raw.decode("utf-8", errors="replace")


def sanitize_id_component(s: str) -> str:
    s = s.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    return s.strip("_")


def ymd_from_isoish(s: str) -> str:
    m = re.search(r"(\d{4}-\d{2}-\d{2})", s or "")
    return m.group(1) if m else ""


@dataclass(frozen=True)
class WebPage:
    url: str
    title: str
    published_date: str


def sitemap_urls(xml_text: str) -> List[Tuple[str, str]]:
    # Returns list of (loc, lastmod)
    root = ET.fromstring(xml_text)
    ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    out: List[Tuple[str, str]] = []
    for url_el in root.findall("sm:url", ns):
        loc_el = url_el.find("sm:loc", ns)
        if loc_el is None or not (loc_el.text or "").strip():
            continue
        lastmod_el = url_el.find("sm:lastmod", ns)
        out.append(((loc_el.text or "").strip(), (lastmod_el.text or "").strip() if lastmod_el is not None else ""))
    return out


def looks_like_index_url(url: str) -> bool:
    p = urlparse(url)
    path = p.path or "/"
    if path in ("/", "/feed.xml", "/sitemap.xml", "/robots.txt"):
        return True
    if re.fullmatch(r"/page\d+/?", path):
        return True
    return False


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
    t = html.unescape(m.group(1)).strip()
    # Many pages use "<title>Foo - Joscha Bach</title>".
    t = re.sub(r"\s*-\s*Joscha Bach\s*$", "", t).strip()
    return t


def is_article_page(html_text: str) -> bool:
    og_type = extract_meta(html_text, "og:type").lower()
    if og_type == "article":
        return True
    # Some pages omit og:type but include article:published_time.
    if extract_meta(html_text, "article:published_time"):
        return True
    return False


def parse_article_page(url: str, html_text: str, lastmod: str) -> Optional[WebPage]:
    if not is_article_page(html_text):
        return None

    title = extract_title(html_text)
    published = ymd_from_isoish(extract_meta(html_text, "article:published_time"))
    if not published:
        published = ymd_from_isoish(lastmod)
    return WebPage(url=url, title=title, published_date=published)


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


def url_slug(url: str) -> str:
    p = urlparse(url)
    slug = p.path.strip("/")
    if not slug:
        slug = "root"
    return sanitize_id_component(slug)


def upsert_bachai_rows(
    existing_rows: List[Dict[str, str]],
    existing_by_id: Dict[str, Dict[str, str]],
    pages: List[WebPage],
    notes_suffix: str,
) -> List[Dict[str, str]]:
    new_rows = list(existing_rows)

    for page in pages:
        sid = f"web_bachai_{url_slug(page.url)}"
        row = existing_by_id.get(sid)
        if row is None:
            row = {
                "source_id": sid,
                "title": page.title,
                "kind": "web",
                "creator_or_channel": "bach.ai",
                "url": page.url,
                "published_date": page.published_date,
                "language": "",
                "notes": notes_suffix,
            }
            new_rows.append(row)
            existing_by_id[sid] = row
            continue

        if not row.get("title") and page.title:
            row["title"] = page.title
        if not row.get("kind"):
            row["kind"] = "web"
        if not row.get("creator_or_channel"):
            row["creator_or_channel"] = "bach.ai"
        if not row.get("url"):
            row["url"] = page.url
        if not row.get("published_date") and page.published_date:
            row["published_date"] = page.published_date

    def sort_key(r: Dict[str, str]) -> Tuple[str, str]:
        d = r.get("published_date") or ""
        return ("" if d else "1") + d, r.get("source_id") or ""

    new_rows.sort(key=sort_key)
    new_rows.reverse()
    return new_rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default="sources/sources.csv", help="canonical sources CSV")
    ap.add_argument("--sitemap", default=SITEMAP_URL, help="bach.ai sitemap URL (HTTP)")
    ap.add_argument(
        "--notes",
        default="discovered_via=bach.ai sitemap",
        help="notes string to attach to newly-added rows",
    )
    args = ap.parse_args()

    sm = fetch_text(args.sitemap)
    locs = sitemap_urls(sm)

    pages: List[WebPage] = []
    for loc, lastmod in locs:
        if looks_like_index_url(loc):
            continue
        try:
            page_html = fetch_text(loc)
        except Exception:
            continue
        page = parse_article_page(loc, page_html, lastmod)
        if page is None:
            continue
        pages.append(page)

    csv_path = Path(args.csv)
    existing_rows, existing_by_id = read_sources_csv(csv_path)
    merged = upsert_bachai_rows(existing_rows, existing_by_id, pages, args.notes)
    write_sources_csv(csv_path, merged)

    print(f"Imported {len(pages)} bach.ai articles -> {csv_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
