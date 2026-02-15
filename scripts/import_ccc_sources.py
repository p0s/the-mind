#!/usr/bin/env python3
"""
Import Joscha Bach talks from media.ccc.de into sources/sources.csv.

Discovery:
  - Fetch https://media.ccc.de/search?p=Joscha
  - Extract /v/... talk links

Filter:
  - Keep only talks whose speaker list contains "Joscha" or "Joscha Bach".
    (media.ccc.de often stores him as just "Joscha".)

Metadata extraction (from talk page HTML):
  - title: <meta property="og:title" ...>
  - published_date: <meta property="og:video:release_date" ...> (YYYY-MM-DD)
"""

from __future__ import annotations

import argparse
import csv
import html
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlparse
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
CCC_BASE = "https://media.ccc.de"
CCC_SEARCH = "https://media.ccc.de/search?p=Joscha"


def fetch_text(url: str) -> str:
    req = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(req, timeout=60) as resp:
        raw = resp.read()
    return raw.decode("utf-8", errors="replace")


def sanitize_id_component(s: str) -> str:
    # Keep stable-ish ASCII IDs.
    s = s.strip()
    s = re.sub(r"[^A-Za-z0-9]+", "_", s)
    return s.strip("_")


def ymd_from_ccc_release_date(s: str) -> str:
    m = re.search(r"(\d{4}-\d{2}-\d{2})", s or "")
    return m.group(1) if m else ""


@dataclass(frozen=True)
class CccTalk:
    slug: str
    url: str
    title: str
    published_date: str


def extract_v_links(search_html: str) -> List[str]:
    # search page contains href="/v/<slug>"
    links = set(re.findall(r'href="(/v/[^"]+)"', search_html))
    # Filter obvious non-talk endpoints.
    return sorted(links)


def extract_speakers(talk_html: str) -> List[str]:
    # Speakers are shown in a <p class="persons"> ... </p>
    m = re.search(r'<p class="persons">(.*?)</p>', talk_html, flags=re.DOTALL | re.IGNORECASE)
    if not m:
        return []
    block = m.group(1)
    # Anchor text is speaker name (or first name).
    names = re.findall(r">([^<]+)</a>", block)
    return [html.unescape(n).strip() for n in names if n.strip()]


def extract_meta(talk_html: str, property_name: str) -> str:
    # Example: <meta content="Synthetic Sentience" property="og:title">
    m = re.search(
        rf'<meta[^>]+property="{re.escape(property_name)}"[^>]+content="([^"]+)"',
        talk_html,
        flags=re.IGNORECASE,
    )
    if m:
        return html.unescape(m.group(1)).strip()

    # Sometimes content and property may be swapped order.
    m = re.search(
        rf'<meta[^>]+content="([^"]+)"[^>]+property="{re.escape(property_name)}"',
        talk_html,
        flags=re.IGNORECASE,
    )
    if m:
        return html.unescape(m.group(1)).strip()
    return ""


def parse_ccc_talk(url: str, talk_html: str) -> Optional[CccTalk]:
    parsed = urlparse(url)
    slug = parsed.path.split("/v/", 1)[-1].strip("/")
    if not slug:
        return None

    speakers = extract_speakers(talk_html)
    # media.ccc.de sometimes records him as just "Joscha". Unfortunately, there are
    # also unrelated talks with a different speaker named "Joscha". For our book
    # we want to index Joscha Bach's appearances, so we accept either:
    #   - explicit "Joscha Bach", or
    #   - a solo talk where the only listed speaker is "Joscha".
    if "Joscha Bach" in speakers:
        pass
    elif speakers == ["Joscha"]:
        pass
    else:
        return None

    title = extract_meta(talk_html, "og:title")
    if not title:
        # Fallback: page <title> ... - media.ccc.de
        m = re.search(r"<title>\s*(.*?)\s*</title>", talk_html, flags=re.DOTALL | re.IGNORECASE)
        if m:
            title = html.unescape(m.group(1)).strip()
            title = title.replace("- media.ccc.de", "").strip()

    published_date = ymd_from_ccc_release_date(extract_meta(talk_html, "og:video:release_date"))

    return CccTalk(
        slug=slug,
        url=url,
        title=title,
        published_date=published_date,
    )


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


def upsert_ccc_rows(
    existing_rows: List[Dict[str, str]],
    existing_by_id: Dict[str, Dict[str, str]],
    talks: List[CccTalk],
    notes_suffix: str,
) -> List[Dict[str, str]]:
    new_rows = list(existing_rows)

    for t in talks:
        sid = f"ccc_{sanitize_id_component(t.slug)}"
        row = existing_by_id.get(sid)
        if row is None:
            row = {
                "source_id": sid,
                "title": t.title,
                "kind": "ccc",
                "creator_or_channel": "media.ccc.de",
                "url": t.url,
                "published_date": t.published_date,
                "language": "",
                "notes": notes_suffix,
            }
            new_rows.append(row)
            existing_by_id[sid] = row
            continue

        if not row.get("title") and t.title:
            row["title"] = t.title
        if not row.get("kind"):
            row["kind"] = "ccc"
        if not row.get("creator_or_channel"):
            row["creator_or_channel"] = "media.ccc.de"
        if not row.get("url"):
            row["url"] = t.url
        if not row.get("published_date") and t.published_date:
            row["published_date"] = t.published_date

    def sort_key(r: Dict[str, str]) -> Tuple[str, str]:
        d = r.get("published_date") or ""
        return ("" if d else "1") + d, r.get("source_id") or ""

    new_rows.sort(key=sort_key)
    new_rows.reverse()
    return new_rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default="sources/sources.csv", help="canonical sources CSV")
    ap.add_argument(
        "--notes",
        default="discovered_via=media.ccc.de search:Joscha",
        help="notes string to attach to newly-added rows",
    )
    ap.add_argument("--search-url", default=CCC_SEARCH, help="CCC search URL")
    args = ap.parse_args()

    search_html = fetch_text(args.search_url)
    v_links = extract_v_links(search_html)

    talks: List[CccTalk] = []
    for path in v_links:
        talk_url = urljoin(CCC_BASE, path)
        try:
            talk_html = fetch_text(talk_url)
        except Exception:
            continue
        talk = parse_ccc_talk(talk_url, talk_html)
        if talk is None:
            continue
        talks.append(talk)

    csv_path = Path(args.csv)
    existing_rows, existing_by_id = read_sources_csv(csv_path)
    merged = upsert_ccc_rows(existing_rows, existing_by_id, talks, args.notes)
    write_sources_csv(csv_path, merged)

    print(f"Imported {len(talks)} CCC talks -> {csv_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
