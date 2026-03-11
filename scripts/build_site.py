#!/usr/bin/env python3
"""
Build the public V2 static site plus a lightly linked V1 archive.

Outputs to ./dist/ (gitignored). No transcript text is read or emitted.
Optionally, local diarization metadata may be read to enrich cite tooltips.

Public V2 pages:
- index.html
- guide/
- questions/ (+ one page per question)
- map/
- glossary/
- claims/
- sources/
- further-reading/
- archive/
- about/

Archive:
- reader/ (legacy V1 single-page reader)

The site keeps provenance as links to original sources (URL + locator).
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple
from urllib.parse import urljoin


ROOT = Path(__file__).resolve().parents[1]

TEMPLATE_BASE = ROOT / "site" / "templates" / "base.html"
ASSETS_DIR = ROOT / "site" / "assets"
HOME_MD = ROOT / "site" / "home.md"

CHAPTERS_DIR = ROOT / "manuscript" / "chapters"
GUIDE_MD = ROOT / "content" / "guide" / "index.md"
QUESTIONS_DIR = ROOT / "content" / "questions"
QUESTIONS_INDEX_MD = QUESTIONS_DIR / "index.md"
ARCHIVE_MD = ROOT / "content" / "archive" / "index.md"
PUBLIC_GLOSSARY_MD = ROOT / "content" / "glossary" / "index.md"
PUBLIC_CLAIMS_MD = ROOT / "content" / "claims" / "index.md"
BACKEND_GLOSSARY_MD = ROOT / "notes" / "glossary.md"
BACKEND_CLAIMS_MD = ROOT / "notes" / "claims.md"
DOC_SOURCES_MD = ROOT / "docs" / "sources.md"
FURTHER_READING_MD = ROOT / "docs" / "further_reading.md"
SOURCES_CSV = ROOT / "sources" / "sources.csv"
SPEAKERS_DIR = ROOT / "transcripts" / "_speakers"
DEFAULT_SITE_BASE_URL = "https://the-mind.xyz/"


TAG_RX = re.compile(r"^\[(BACH|SYNTH|NOTE|OPEN)\]\s*", re.IGNORECASE)
TIMECODE_RX = r"\d{2}:\d{2}:\d{2}(?:[\\.,]\d{1,3})?"
PAGE_LOCATOR_RX = r"p\d+(?:-\d+)?"
LOCATOR_RX = rf"(?:{TIMECODE_RX}|{PAGE_LOCATOR_RX})"
SRC_RX = re.compile(
    rf"<!--\s*src:\s*([a-z0-9_\\-]+)\s*@\s*({LOCATOR_RX})\s*-->",
    re.IGNORECASE,
)
SRC_COMMENT_RX = re.compile(r"<!--\s*src:\s*([^>]+?)\s*-->", re.IGNORECASE)
SRC_REF_IN_COMMENT_RX = re.compile(rf"([a-z0-9_\-]+)\s*@\s*({LOCATOR_RX})", re.IGNORECASE)
SRC_ITEM_RX = re.compile(rf"^([a-z0-9_\-]+)\s+@\s+({LOCATOR_RX})\b(.*)$", re.IGNORECASE)


def parse_timecode_to_seconds(tc: str) -> Optional[int]:
    m = re.match(r"^(\d{2}):(\d{2}):(\d{2})(?:[\\.,](\d{1,3}))?$", tc.strip())
    if not m:
        return None
    h, mm, ss, _ms = m.groups()
    return int(h) * 3600 + int(mm) * 60 + int(ss)


def timecoded_url(url: str, timecode: str) -> str:
    sec = parse_timecode_to_seconds(timecode)
    if sec is None:
        return url
    u = url.strip()
    if not u:
        return u

    # YouTube
    if "youtube.com/watch" in u:
        join = "&" if "?" in u else "?"
        return f"{u}{join}t={sec}s"
    if "youtu.be/" in u:
        join = "&" if "?" in u else "?"
        return f"{u}{join}t={sec}"

    # media.ccc.de commonly supports ?t=SECONDS
    if "media.ccc.de" in u:
        join = "&" if "?" in u else "?"
        return f"{u}{join}t={sec}"

    return u


def normalize_locator(locator: str) -> str:
    loc = (locator or "").strip().replace("–", "-").replace("—", "-")
    if not loc:
        return loc
    if re.match(rf"^{TIMECODE_RX}$", loc, re.IGNORECASE):
        return loc.replace(",", ".")
    m = re.match(r"^[Pp]\.?\s*(\d+)(?:\s*-\s*(\d+))?$", loc)
    if m:
        start, end = m.groups()
        return f"p{start}-{end}" if end else f"p{start}"
    return loc


def located_url(url: str, locator: str) -> str:
    loc = normalize_locator(locator)
    if re.match(rf"^{TIMECODE_RX}$", loc, re.IGNORECASE):
        return timecoded_url(url, loc)
    m = re.match(r"^p(\d+)(?:-(\d+))?$", loc, re.IGNORECASE)
    if m:
        page = m.group(1)
        return f"{url.strip()}#page={page}"
    return url.strip()


def parse_src_comment_refs(body: str) -> List[Tuple[str, str]]:
    refs: List[Tuple[str, str]] = []
    for sid, loc in SRC_REF_IN_COMMENT_RX.findall(body or ""):
        refs.append((sid, normalize_locator(loc)))
    return refs


def extract_src_comment_refs(text: str) -> Tuple[str, List[Tuple[str, str]]]:
    refs: List[Tuple[str, str]] = []

    def repl(m: re.Match[str]) -> str:
        refs.extend(parse_src_comment_refs(m.group(1)))
        return ""

    cleaned = SRC_COMMENT_RX.sub(repl, text or "")
    return cleaned.strip(), refs


ALLOWED_PRESENTATION_FORMATS = {"talk", "interview", "essay"}

_BACH_TIME_S_CACHE: Dict[str, Optional[int]] = {}


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

    # Minimal, human-oriented synonyms.
    if x in {"podcast", "conversation", "qa"}:
        return "interview"
    if x in {"lecture", "presentation", "keynote"}:
        return "talk"
    if x in {"article", "post", "blog"}:
        return "essay"
    return None


def infer_presentation_format(meta: Dict[str, str]) -> str:
    notes = meta.get("notes") or ""
    kv = parse_notes_kv(notes)
    fmt = normalize_presentation_format(kv.get("format") or "")
    if fmt:
        return fmt

    kind = (meta.get("kind") or "").strip().lower()  # media type; do not display
    url = (meta.get("url") or "").strip().lower()
    title = (meta.get("title") or "").strip().lower()
    creator = (meta.get("creator_or_channel") or "").strip().lower()
    hay = " ".join([title, creator])

    # Written sources.
    if kind in {"web"}:
        return "essay"

    # CCC recordings are almost always talks.
    if "media.ccc.de" in url or kind in {"ccc"}:
        return "talk"

    # Heuristics for common YouTube naming conventions.
    if any(w in hay for w in ("interview", "podcast", "conversation", "salon", "debate", "q&a", "qa")):
        return "interview"
    if any(w in hay for w in ("lex fridman", "curt jaimungal", "street talk")):
        return "interview"

    # Default: a talk/lecture-style presentation.
    return "talk"


def seconds_to_hhmmss(total_s: int) -> str:
    s = max(0, int(total_s))
    h = s // 3600
    s -= h * 3600
    m = s // 60
    s -= m * 60
    return f"{h:02d}:{m:02d}:{s:02d}"


def bach_time_seconds(source_id: str) -> Optional[int]:
    """
    Optional local-only enrichment: approximate total seconds attributed to Joscha Bach.
    Requires transcripts/_speakers/<source_id>.speakers.json (typically gitignored).
    """
    if source_id in _BACH_TIME_S_CACHE:
        return _BACH_TIME_S_CACHE[source_id]
    if not SPEAKERS_DIR.exists():
        _BACH_TIME_S_CACHE[source_id] = None
        return None

    p = SPEAKERS_DIR / f"{source_id}.speakers.json"
    if not p.exists():
        _BACH_TIME_S_CACHE[source_id] = None
        return None

    try:
        data = json.loads(p.read_text(encoding="utf-8", errors="replace"))
        segs = data.get("bach_segments") or []
        total = 0.0
        for seg in segs:
            if not isinstance(seg, dict):
                continue
            start = seg.get("start_s")
            end = seg.get("end_s")
            if isinstance(start, (int, float)) and isinstance(end, (int, float)) and end > start:
                total += float(end) - float(start)
        secs = int(round(total))
        if secs <= 0:
            secs = None
    except Exception:
        secs = None

    _BACH_TIME_S_CACHE[source_id] = secs
    return secs


def render_cite_link(source_id: str, locator: str, sources: Dict[str, Dict[str, str]], *, show_time: bool) -> Optional[str]:
    meta = sources.get(source_id, {})
    url = (meta.get("url") or "").strip()
    if not url:
        return None

    loc = normalize_locator(locator)
    href = located_url(url, loc)

    fmt = infer_presentation_format(meta)
    title = re.sub(r"\s+", " ", (meta.get("title") or "").strip()) or source_id
    label = f"{fmt}: {title}"

    tooltip_lines = [f"{fmt}: {title}", f"{source_id} @ {loc}"]
    bach_s = bach_time_seconds(source_id)
    if bach_s is not None:
        tooltip_lines.append(f"Bach time: {seconds_to_hhmmss(bach_s)} (approx)")
    tooltip = " | ".join(tooltip_lines)

    a = (
        f'<a class="cite" href="{escape_attr(href)}" target="_blank" rel="noopener noreferrer" title="{escape_attr(tooltip)}">{escape(label)}</a>'
    )
    if show_time:
        return f'<span class="cite_ref">{a}<span class="cite_time">@ {escape(loc)}</span></span>'
    return a


def render_cite_group(source_id: str, locators: List[str], sources: Dict[str, Dict[str, str]], *, show_time: bool) -> Optional[str]:
    meta = sources.get(source_id, {})
    url = (meta.get("url") or "").strip()
    if not url or not locators:
        return None

    normalized = []
    seen = set()
    for loc in locators:
        norm = normalize_locator(loc)
        if not norm or norm in seen:
            continue
        seen.add(norm)
        normalized.append(norm)
    if not normalized:
        return None

    href = located_url(url, normalized[0])
    fmt = infer_presentation_format(meta)
    title = re.sub(r"\s+", " ", (meta.get("title") or "").strip()) or source_id
    label = f"{fmt}: {title}"
    locator_text = ", ".join(normalized)

    tooltip_lines = [f"{fmt}: {title}", f"{source_id} @ {locator_text}"]
    bach_s = bach_time_seconds(source_id)
    if bach_s is not None:
        tooltip_lines.append(f"Bach time: {seconds_to_hhmmss(bach_s)} (approx)")
    tooltip = " | ".join(tooltip_lines)

    a = (
        f'<a class="cite" href="{escape_attr(href)}" target="_blank" rel="noopener noreferrer" title="{escape_attr(tooltip)}">{escape(label)}</a>'
    )
    if show_time or len(normalized) > 1:
        return f'<span class="cite_ref">{a}<span class="cite_time">@ {escape(locator_text)}</span></span>'
    return a


def render_cite_refs(
    refs: List[Tuple[str, str]],
    sources: Dict[str, Dict[str, str]],
    *,
    show_time: bool,
) -> str:
    grouped: List[Tuple[str, List[str]]] = []
    order: Dict[str, int] = {}
    for sid, loc in refs:
        if sid not in order:
            order[sid] = len(grouped)
            grouped.append((sid, [loc]))
            continue
        grouped[order[sid]][1].append(loc)

    rendered: List[str] = []
    for sid, locators in grouped:
        html = render_cite_group(sid, locators, sources, show_time=show_time)
        if html:
            rendered.append(html)
    return " ".join(rendered)


def linkify_source_ref(text: str, sources: Dict[str, Dict[str, str]], *, root: str) -> Optional[str]:
    """
    Turn "source_id @ <locator> ..." into a link to the canonical URL (+ locator).

    This is primarily for "Anchors (sources + timecodes)" lists, but it also
    helps on glossary/claims pages where we cite with the same syntax.
    """
    m = SRC_ITEM_RX.match(text.strip())
    if not m:
        return None
    sid, loc, rest = m.groups()
    linked = render_cite_link(sid, loc, sources, show_time=True)
    if not linked:
        return None
    # Keep any trailing details (e.g. "(keywords: ...)") readable and searchable.
    tail = inline_format(rest, root=root) if rest else ""
    return linked + tail


def render_mermaid_svg(code: str) -> Optional[str]:
    src = code.strip()
    if not src:
        return None

    node = shutil.which("node")
    if not node:
        return None

    renderer = ROOT / "scripts" / "render_mermaid_svg.mjs"
    if not renderer.exists():
        return None

    try:
        cp = subprocess.run(
            [node, str(renderer)],
            input=src + "\n",
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
    except Exception:
        return None
    if cp.returncode != 0:
        return None

    svg = (cp.stdout or "").strip()
    svg = re.sub(r"^<\\?xml[^>]*>\\s*", "", svg)
    if "<svg" not in svg:
        return None
    return svg


def load_sources() -> Dict[str, Dict[str, str]]:
    out: Dict[str, Dict[str, str]] = {}
    with SOURCES_CSV.open("r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            sid = (row.get("source_id") or "").strip()
            if not sid:
                continue
            out[sid] = dict(row)
    return out


def escape(s: str) -> str:
    return html.escape(s, quote=False)


def escape_attr(s: str) -> str:
    return html.escape(s, quote=True)


CLM_ID_RX = re.compile(r"\bCLM-(\d{4})\b", re.IGNORECASE)
TERM_ID_RX = re.compile(r"\bTERM-(\d{4})\b", re.IGNORECASE)


def normalize_site_href(href: str, *, root: str) -> str:
    raw = (href or "").strip()
    if not raw or raw.startswith(("http://", "https://", "mailto:", "#")):
        return raw

    if raw.startswith(("./", "../")):
        return raw

    # Treat leading-slash links as site-root links and rewrite them relative
    # to the current page depth so the static build works on nested routes.
    path = raw[1:] if raw.startswith("/") else raw
    query = ""
    fragment = ""
    if "#" in path:
        path, fragment = path.split("#", 1)
        fragment = "#" + fragment
    if "?" in path:
        path, query = path.split("?", 1)
        query = "?" + query

    path = path.lstrip("./")
    if not path:
        return root.rstrip("/") + "/" + query + fragment
    if not path.endswith("/") and not Path(path).suffix:
        path += "/"
    if path.endswith("/"):
        path += "index.html"
    return root + path + query + fragment


def page_root(href: str) -> str:
    rel = (href or "").strip().lstrip("./")
    if not rel:
        return "./"
    parts = [p for p in rel.split("/") if p]
    depth = max(0, len(parts) - 1)
    if depth <= 0:
        return "./"
    return "../" * depth


def markdown_title(md: str, fallback: str) -> str:
    h1 = next((l[2:].strip() for l in md.splitlines() if l.startswith("# ")), "")
    title = re.sub(r"\s+", " ", h1 or fallback).strip()
    return title or fallback


def read_markdown_or_missing(path: Path, fallback_title: str) -> str:
    if path.exists():
        return path.read_text(encoding="utf-8", errors="replace")
    return f"# {fallback_title}\n\n_{fallback_title} content missing: {path.relative_to(ROOT)}._\n"


def inline_format(s: str, *, root: str) -> str:
    # Conservative inline formatting:
    # - Escape text
    # - Protect code/links from emphasis processing
    # - Apply bold/italics to remaining text only
    s = escape(s)
    protected: List[str] = []

    def stash(fragment: str) -> str:
        token = f"@@FMT{len(protected)}@@"
        protected.append(fragment)
        return token

    # `code`
    s = re.sub(r"`([^`]+)`", lambda m: stash(f"<code>{m.group(1)}</code>"), s)

    # [text](url)
    def make_anchor(label: str, href: str) -> str:
        norm_href = normalize_site_href(href, root=root)
        # `href` is already escaped except for quotes (escape() uses quote=False).
        href_attr = norm_href.replace('"', "&quot;").replace("'", "&#x27;")
        if norm_href.startswith(("http://", "https://")):
            return f'<a href="{href_attr}" target="_blank" rel="noopener noreferrer">{label}</a>'
        return f'<a href="{href_attr}">{label}</a>'

    s = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", lambda m: stash(make_anchor(m.group(1), m.group(2))), s)

    # Bare URLs
    s = re.sub(
        r"(?<![\"'=])(https?://[^\s<>()]+)",
        lambda m: stash(make_anchor(m.group(1), m.group(1))),
        s,
    )

    # Cross-link stable knowledge-base IDs.
    s = re.sub(
        CLM_ID_RX,
        lambda m: stash(make_anchor(m.group(0), f"{root}claims/index.html#clm-{m.group(1)}")),
        s,
    )
    s = re.sub(
        TERM_ID_RX,
        lambda m: stash(make_anchor(m.group(0), f"{root}glossary/index.html#term-{m.group(1)}")),
        s,
    )

    # **bold**
    s = re.sub(r"\*\*([^*]+)\*\*", lambda m: f"<strong>{m.group(1)}</strong>", s)
    # *italics* and _italics_ (keep conservative boundaries)
    s = re.sub(r"(?<!\w)\*([^*\n]+?)\*(?!\w)", lambda m: f"<em>{m.group(1)}</em>", s)
    s = re.sub(r"(?<!\w)_([^_\n]+?)_(?!\w)", lambda m: f"<em>{m.group(1)}</em>", s)

    # Restore protected fragments (code/links) after emphasis processing.
    for idx, frag in enumerate(protected):
        s = s.replace(f"@@FMT{idx}@@", frag)
    return s


def strip_md_for_search(s: str) -> str:
    s = TAG_RX.sub("", s)
    s = SRC_COMMENT_RX.sub("", s)
    s = re.sub(r"<!--\s*chapter_keywords:\s*.*?-->", "", s, flags=re.IGNORECASE)
    s = re.sub(r"`([^`]+)`", r"\1", s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"\1", s)
    s = re.sub(r"(?<!\w)\*([^*\n]+?)\*(?!\w)", r"\1", s)
    s = re.sub(r"(?<!\w)_([^_\n]+?)_(?!\w)", r"\1", s)
    s = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def slugify(s: str) -> str:
    s = s.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = re.sub(r"-{2,}", "-", s).strip("-")
    return s or "section"


@dataclass
class Block:
    kind: str  # heading|para|list|blockquote|code|hr
    tag: str  # BACH|SYNTH|NOTE|OPEN|""  (internal)
    text: str
    level: int = 0  # for headings
    ordered: bool = False  # for lists
    items: Optional[List[str]] = None  # for lists
    code_lang: str = ""
    code: str = ""
    anchor: Optional[Tuple[str, str]] = None  # (source_id, locator)
    anchors: Optional[List[Tuple[str, str]]] = None


def parse_blocks(md: str) -> List[Block]:
    lines = md.splitlines()
    blocks: List[Block] = []

    in_code = False
    code_lang = ""
    code_lines: List[str] = []

    pending_tag: str = ""
    pending_anchor: Optional[Tuple[str, str]] = None
    pending_anchors: Optional[List[Tuple[str, str]]] = None

    cur_para: List[str] = []
    cur_list: List[str] = []
    cur_list_ordered = False
    cur_quote: List[str] = []

    def flush_para() -> None:
        nonlocal cur_para, pending_tag, pending_anchor, pending_anchors
        if not cur_para:
            return
        text = " ".join([p.strip() for p in cur_para]).strip()
        tag = pending_tag
        anchor = pending_anchor
        anchors: List[Tuple[str, str]] = list(pending_anchors or ([] if not anchor else [anchor]))
        pending_tag = ""
        pending_anchor = None
        pending_anchors = None

        text, inline_refs = extract_src_comment_refs(text)
        if inline_refs:
            anchor = inline_refs[0]
            anchors = inline_refs

        blocks.append(
            Block(
                kind="para",
                tag=tag,
                text=text,
                anchor=anchor,
                anchors=anchors or None,
            )
        )
        cur_para = []

    def flush_list() -> None:
        nonlocal cur_list, cur_list_ordered, pending_tag, pending_anchor, pending_anchors
        if not cur_list:
            return
        tag = pending_tag
        anchor = pending_anchor
        anchors: Optional[List[Tuple[str, str]]] = list(pending_anchors or ([] if not anchor else [anchor])) or None
        pending_tag = ""
        pending_anchor = None
        pending_anchors = None
        blocks.append(
            Block(
                kind="list",
                tag=tag,
                text="",
                ordered=cur_list_ordered,
                items=cur_list[:],
                anchor=anchor,
                anchors=anchors,
            )
        )
        cur_list = []
        cur_list_ordered = False

    def flush_quote() -> None:
        nonlocal cur_quote
        if not cur_quote:
            return
        blocks.append(Block(kind="blockquote", tag="", text="\n".join(cur_quote).rstrip("\n")))
        cur_quote = []

    for raw in lines:
        line = raw.rstrip("\n")

        if line.strip().lower().startswith("<!-- chapter_keywords:"):
            continue

        if in_code:
            if line.strip().startswith("```"):
                blocks.append(Block(kind="code", tag="", text="", code_lang=code_lang, code="\n".join(code_lines).rstrip()))
                in_code = False
                code_lang = ""
                code_lines = []
            else:
                code_lines.append(line)
            continue

        if line.strip().startswith("```"):
            flush_para()
            flush_list()
            flush_quote()
            in_code = True
            code_lang = line.strip()[3:].strip()
            code_lines = []
            continue

        if line.strip() == "---":
            flush_para()
            flush_list()
            flush_quote()
            blocks.append(Block(kind="hr", tag="", text=""))
            continue

        # Headings
        if line.startswith("#"):
            m = re.match(r"^(#{1,6})\s+(.*)$", line)
            if m:
                flush_para()
                flush_list()
                flush_quote()
                level = len(m.group(1))
                blocks.append(Block(kind="heading", tag="", text=m.group(2).strip(), level=level))
                continue

        if cur_quote and not line.lstrip().startswith(">"):
            flush_quote()

        # Tag lines: may apply to this line or the next block.
        tag = ""
        rest = line
        m = TAG_RX.match(rest)
        if m:
            tag = m.group(1).upper()
            rest = TAG_RX.sub("", rest).strip()
            # Extract anchor comment from remainder (even if remainder is otherwise empty).
            rest, inline_refs = extract_src_comment_refs(rest)
            if inline_refs:
                pending_anchor = inline_refs[0]
                pending_anchors = inline_refs
            if not rest:
                pending_tag = tag
                continue
            # Otherwise the tag applies to the paragraph that starts here.
            pending_tag = tag
            line = rest

        # Lists
        if line.lstrip().startswith("- "):
            flush_para()
            flush_quote()
            item = line.lstrip()[2:].strip()
            cur_list.append(item)
            cur_list_ordered = False
            continue

        m_ol = re.match(r"^\s*\d+\.\s+(.*)$", line)
        if m_ol:
            flush_para()
            flush_quote()
            cur_list.append(m_ol.group(1).strip())
            cur_list_ordered = True
            continue

        # Support a simple wrapped continuation line inside the current list item.
        if cur_list and re.match(r"^\s{2,}\S", line):
            cur_list[-1] = cur_list[-1].rstrip() + "\n" + line.strip()
            continue

        # Blockquotes (epigraph-style; keep line breaks)
        if line.lstrip().startswith(">"):
            flush_para()
            flush_list()
            q = line.lstrip()[1:]
            if q.startswith(" "):
                q = q[1:]
            cur_quote.append(q.rstrip())
            continue

        # Blank line separates blocks.
        if not line.strip():
            flush_para()
            flush_list()
            flush_quote()
            continue

        # Normal paragraph text
        flush_quote()
        cur_para.append(line.strip())

    flush_para()
    flush_list()
    flush_quote()

    return blocks


_CLAIM_HEAD_ID_RX = re.compile(r"^(CLM-\d{4})\b", re.IGNORECASE)
_TERM_ID_ITEM_RX = re.compile(r"^Id:\s*(TERM-\d{4})\s*$", re.IGNORECASE)


def blocks_to_html(
    blocks: List[Block],
    sources: Dict[str, Dict[str, str]],
    *,
    root: str,
    page_kind: str = "",
) -> Tuple[str, str]:
    parts: List[str] = []
    search_parts: List[str] = []
    seen_ids: Dict[str, int] = {}

    glossary_heading_ids: Dict[int, str] = {}
    if page_kind == "glossary":
        for i, b in enumerate(blocks):
            if b.kind != "heading" or b.level != 2:
                continue
            term_id = None
            for j in range(i + 1, len(blocks)):
                nxt = blocks[j]
                if nxt.kind == "heading" and nxt.level == 2:
                    break
                if nxt.kind != "list":
                    continue
                for it in nxt.items or []:
                    m = _TERM_ID_ITEM_RX.match((it or "").strip())
                    if not m:
                        continue
                    term_id = m.group(1).lower()
                    break
                if term_id:
                    break
            if term_id:
                glossary_heading_ids[i] = term_id

    for i, b in enumerate(blocks):
        if b.kind == "heading":
            txt = inline_format(b.text, root=root)
            base = slugify(b.text)
            if page_kind == "claims" and b.level == 2:
                m = _CLAIM_HEAD_ID_RX.match((b.text or "").strip())
                if m:
                    base = m.group(1).lower()
            if page_kind == "glossary" and b.level == 2:
                base = glossary_heading_ids.get(i, base)
            n = seen_ids.get(base, 0)
            seen_ids[base] = n + 1
            hid = base if n == 0 else f"{base}-{n+1}"
            parts.append(f'<h{b.level} id="{escape(hid)}">{txt}</h{b.level}>')
            search_parts.append(strip_md_for_search(b.text))
            continue
        if b.kind == "hr":
            parts.append("<hr />")
            continue
        if b.kind == "blockquote":
            clean_text, refs = extract_src_comment_refs(b.text)
            lines = [ln for ln in clean_text.split("\n")]
            inner = "<br />".join([inline_format(ln, root=root) for ln in lines])
            cite_html = ""
            rendered_refs = render_cite_refs(refs, sources, show_time=False)
            if rendered_refs:
                cite_html = " " + rendered_refs
            parts.append(f"<blockquote><p>{inner}{cite_html}</p></blockquote>")
            search_parts.append(strip_md_for_search(clean_text))
            continue
        if b.kind == "code":
            if b.code_lang.strip().lower() == "mermaid":
                # Mermaid rendering currently produces empty diagrams in the reader UI.
                # Omit diagrams for now (keep the source in markdown; re-enable later).
                continue
            cls = f"language-{escape(b.code_lang)}" if b.code_lang else ""
            parts.append(f'<pre><code class="{cls}">{escape(b.code)}</code></pre>')
            continue
        if b.kind == "list":
            tag_attr = f' data-tag="{b.tag}"' if b.tag else ""
            wrap_open = f'<div class="blk"{tag_attr}>' if b.tag else ""
            wrap_close = "</div>" if b.tag else ""
            if b.tag:
                parts.append(wrap_open + f'<span class="pill">{escape(b.tag)}</span>')
            tag_list = "ol" if b.ordered else "ul"
            parts.append(f"<{tag_list}>")
            for it in b.items or []:
                clean_item, item_refs = extract_src_comment_refs(it)
                linked = linkify_source_ref(clean_item, sources, root=root)
                if linked:
                    rendered_item = linked
                else:
                    rendered_item = "<br />".join([inline_format(part, root=root) for part in clean_item.split("\n")])
                rendered_refs = render_cite_refs(item_refs, sources, show_time=False)
                if rendered_refs:
                    rendered_item += " " + rendered_refs
                parts.append(f"<li>{rendered_item}</li>")
                search_parts.append(strip_md_for_search(clean_item))
            parts.append(f"</{tag_list}>")
            rendered_refs = render_cite_refs(b.anchors or ([] if not b.anchor else [b.anchor]), sources, show_time=False)
            if rendered_refs:
                parts.append(rendered_refs)
            if b.tag:
                parts.append(wrap_close)
            continue
        if b.kind == "para":
            tag_attr = f' data-tag="{b.tag}"' if b.tag else ""
            wrap_open = f'<div class="blk"{tag_attr}>' if b.tag else ""
            wrap_close = "</div>" if b.tag else ""
            if b.tag:
                parts.append(wrap_open + f'<span class="pill">{escape(b.tag)}</span>')
            txt = inline_format(b.text, root=root)
            rendered_refs = render_cite_refs(b.anchors or ([] if not b.anchor else [b.anchor]), sources, show_time=False)
            cite_html = (" " + rendered_refs) if rendered_refs else ""
            parts.append(f"<p>{txt}{cite_html}</p>")
            if b.tag:
                parts.append(wrap_close)
            search_parts.append(strip_md_for_search(b.text))
            continue

    return "\n".join(parts), " ".join([p for p in search_parts if p]).strip()


def read_template() -> str:
    return TEMPLATE_BASE.read_text(encoding="utf-8", errors="replace")


def site_base_url() -> str:
    v = (os.environ.get("THE_MIND_SITE_BASE_URL") or "").strip()
    if not v:
        v = DEFAULT_SITE_BASE_URL
    if not v.endswith("/"):
        v += "/"
    return v


def canonical_rel_path(href: str) -> str:
    rel = (href or "").strip().lstrip("./")
    if not rel or rel == "index.html":
        return ""
    if rel.endswith("/index.html"):
        return rel[: -len("index.html")]
    return rel


def absolute_page_url(base_url: str, href: str) -> str:
    return urljoin(base_url, canonical_rel_path(href))


def render_page(
    template: str,
    *,
    title: str,
    nav: str,
    content: str,
    root: str,
    page_id: str,
    page_url: str,
    og_image_url: str,
    body_class: str = "",
    extra_scripts: str = "",
) -> str:
    return (
        template.replace("{{title}}", escape(title))
        .replace("{{nav}}", nav)
        .replace("{{content}}", content)
        .replace("{{root}}", root)
        .replace("{{page_id}}", escape(page_id))
        .replace("{{page_url}}", escape_attr(page_url))
        .replace("{{og_image_url}}", escape_attr(og_image_url))
        .replace("{{body_class}}", escape(body_class))
        .replace("{{extra_scripts}}", extra_scripts)
    )


def emit_markdown_page(
    *,
    out_dir: Path,
    template: str,
    sources: Dict[str, Dict[str, str]],
    href: str,
    title: str,
    md: str,
    page_kind: str,
    base_url: str,
    og_image_url: str,
    nav_html: str,
) -> Tuple[str, str]:
    root = page_root(href)
    html_body, text_body = blocks_to_html(parse_blocks(md), sources, root=root, page_kind=page_kind)
    body_class = "supports-annotations" if href == "reader/index.html" else ""
    write(
        out_dir / href,
        render_page(
            template,
            title=title,
            nav=nav_html,
            content=html_body,
            root=root,
            page_id=slugify(href.replace("/index.html", "").replace("/", "-") or "home"),
            page_url=absolute_page_url(base_url, href),
            og_image_url=og_image_url,
            body_class=body_class,
        ),
    )
    return html_body, text_body


def build_nav(
    question_pages: List[Tuple[str, str]],
    *,
    current_href: str,
    root: str,
) -> str:
    def is_current(href: str) -> bool:
        return href == current_href

    def a(href: str, label: str) -> str:
        cur = ' aria-current="page"' if is_current(href) else ""
        return f'<a href="{escape(root + href)}"{cur}>{escape(label)}</a>'

    parts: List[str] = []
    parts.append('<div class="nav">')
    parts.append('<div class="navgroup">')
    parts.append('<div class="navtitle">Read</div>')
    parts.append(a("index.html", "Home"))
    parts.append(a("guide/index.html", "How the Mind Works"))
    q_open = current_href.startswith("questions/")
    parts.append(f'<details class="navdetails"{" open" if q_open else ""}>')
    parts.append(
        '<summary class="navsummary navsummary--linked">'
        + a("questions/index.html", "Questions")
        + "</summary>"
    )
    for href, title in question_pages:
        parts.append(a(href, title))
    parts.append("</details>")
    parts.append("</div>")

    audit_open = current_href.startswith(("glossary/", "claims/", "sources/", "further-reading/"))
    parts.append('<div class="navgroup">')
    parts.append('<div class="navtitle">Audit Layer</div>')
    parts.append(f'<details class="navdetails"{" open" if audit_open else ""}>')
    parts.append('<summary class="navsummary">Glossary And Sources</summary>')
    parts.append(a("glossary/index.html", "Glossary"))
    parts.append(a("claims/index.html", "Claims"))
    parts.append(a("sources/index.html", "Sources"))
    parts.append(a("further-reading/index.html", "Further Reading"))
    parts.append("</details>")
    parts.append("</div>")

    parts.append("</div>")
    return "\n".join(parts)


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def copy_assets(out_dir: Path) -> None:
    dst = out_dir / "assets"
    dst.mkdir(parents=True, exist_ok=True)
    for p in ASSETS_DIR.glob("*"):
        if p.is_file():
            shutil.copy2(p, dst / p.name)


def copy_root_assets(out_dir: Path) -> None:
    """
    Copy a few conventional top-level assets for better UX / link previews.

    We still keep the canonical files under site/assets/; this just provides
    stable root paths like /favicon.ico and /og.png.
    """
    for name in ("favicon.ico", "favicon.svg", "apple-touch-icon.png", "og.png"):
        p = ASSETS_DIR / name
        if p.is_file():
            shutil.copy2(p, out_dir / name)


def write_nojekyll(out_dir: Path) -> None:
    # Makes branch-based Pages deployments work (no Jekyll processing).
    (out_dir / ".nojekyll").write_text("", encoding="utf-8")


def write_sitemap(out_dir: Path, base_url: str, hrefs: Iterable[str]) -> None:
    urls = sorted({absolute_page_url(base_url, href) for href in hrefs})
    parts = ['<?xml version="1.0" encoding="UTF-8"?>']
    parts.append('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">')
    for u in urls:
        parts.append(f"  <url><loc>{escape(u)}</loc></url>")
    parts.append("</urlset>")
    (out_dir / "sitemap.xml").write_text("\n".join(parts) + "\n", encoding="utf-8")


def write_robots(out_dir: Path, base_url: str) -> None:
    sitemap_url = absolute_page_url(base_url, "sitemap.xml")
    text = "\n".join(
        [
            "User-agent: *",
            "Disallow:",
            "",
            f"Sitemap: {sitemap_url}",
            "",
        ]
    )
    (out_dir / "robots.txt").write_text(text, encoding="utf-8")


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "dist"), help="Output directory (default: ./dist)")
    args = ap.parse_args(argv)

    out_dir = Path(args.out)
    # Keep builds reproducible (no stale files) while being careful about what we delete.
    out_abs = out_dir.resolve()
    root_abs = ROOT.resolve()
    if out_abs in {Path("/"), root_abs, root_abs.parent}:
        raise SystemExit(f"Refusing to delete unsafe output dir: {out_abs}")
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    copy_assets(out_dir)
    copy_root_assets(out_dir)
    write_nojekyll(out_dir)

    sources = load_sources()
    template = read_template()
    base_url = site_base_url()
    og_image_url = absolute_page_url(base_url, "og.png")

    # Collect chapters (used for Reader + nav; we do not emit per-chapter pages).
    chapter_files = sorted(CHAPTERS_DIR.glob("ch*.md"))
    chapter_pages: List[Tuple[str, str, str, str]] = []  # (anchor_id, title, src_path, h1)
    for p in chapter_files:
        md = p.read_text(encoding="utf-8", errors="replace")
        h1 = next((l[2:].strip() for l in md.splitlines() if l.startswith("# ")), p.stem)
        title = re.sub(r"^Chapter\s+\d+:\s*", "", h1).strip()
        anchor_id = slugify(h1)
        chapter_pages.append((anchor_id, title, str(p), h1))

    question_files = sorted([p for p in QUESTIONS_DIR.glob("*.md") if p.is_file() and p.name != "index.md"])
    question_pages: List[Tuple[str, str, Path]] = []
    for p in question_files:
        md = p.read_text(encoding="utf-8", errors="replace")
        question_pages.append((f"questions/{p.stem}/index.html", markdown_title(md, p.stem.replace("-", " ")), p))
    question_nav = [(href, title) for href, title, _path in question_pages]

    search_index: List[Dict[str, str]] = []
    page_hrefs: List[str] = []

    def nav_for(href: str) -> str:
        return build_nav(question_nav, current_href=href, root=page_root(href))

    def emit(href: str, title: str, md: str, *, page_kind: str = "") -> None:
        _html_body, text_body = emit_markdown_page(
            out_dir=out_dir,
            template=template,
            sources=sources,
            href=href,
            title=title,
            md=md,
            page_kind=page_kind,
            base_url=base_url,
            og_image_url=og_image_url,
            nav_html=nav_for(href),
        )
        page_hrefs.append(href)
        search_index.append({"href": href, "title": title, "text": text_body})

    emit("index.html", "the-mind", read_markdown_or_missing(HOME_MD, "the-mind"))

    guide_md = read_markdown_or_missing(GUIDE_MD, "How the Mind Works")
    emit("guide/index.html", markdown_title(guide_md, "How the Mind Works"), guide_md)

    questions_index_md = read_markdown_or_missing(QUESTIONS_INDEX_MD, "Questions")
    emit("questions/index.html", markdown_title(questions_index_md, "Questions"), questions_index_md)

    for href, title, path in question_pages:
        emit(href, title, path.read_text(encoding="utf-8", errors="replace"))

    archive_md = read_markdown_or_missing(ARCHIVE_MD, "Archive")
    if chapter_pages and "(/reader/)" not in archive_md:
        archive_md = archive_md.rstrip() + "\n\n## V1 reader\n\n- [Reader / V1 / source-grounded thesis](/reader/)\n"
    emit("archive/index.html", markdown_title(archive_md, "Archive"), archive_md)

    glossary_md_path = PUBLIC_GLOSSARY_MD if PUBLIC_GLOSSARY_MD.exists() else BACKEND_GLOSSARY_MD
    if glossary_md_path.exists():
        glossary_md = glossary_md_path.read_text(encoding="utf-8", errors="replace")
        emit("glossary/index.html", markdown_title(glossary_md, "Glossary"), glossary_md, page_kind="glossary")

    claims_md_path = PUBLIC_CLAIMS_MD if PUBLIC_CLAIMS_MD.exists() else BACKEND_CLAIMS_MD
    if claims_md_path.exists():
        claims_md = claims_md_path.read_text(encoding="utf-8", errors="replace")
        emit("claims/index.html", markdown_title(claims_md, "Claims"), claims_md, page_kind="claims")

    if DOC_SOURCES_MD.exists():
        sources_md = DOC_SOURCES_MD.read_text(encoding="utf-8", errors="replace")
    else:
        keep = []
        for sid, row in sources.items():
            notes = (row.get("notes") or "")
            if "curation_status=keep" in notes:
                keep.append((sid, row))
        keep.sort(key=lambda t: ((t[1].get("published_date") or ""), t[0]))
        src_lines = ["# Sources", "", "Keystone/kept sources referenced by the project.", ""]
        for sid, row in keep:
            title = (row.get("title") or "").strip() or sid
            url = (row.get("url") or "").strip()
            date = (row.get("published_date") or "").strip()
            creator = (row.get("creator_or_channel") or "").strip()
            head = f"- `{sid}`"
            if date:
                head += f" ({date})"
            head += f": {title}"
            if creator:
                head += f" — {creator}"
            if url:
                head += f" — [source]({url})"
            src_lines.append(head)
        sources_md = "\n".join(src_lines) + "\n"
    emit("sources/index.html", markdown_title(sources_md, "Sources"), sources_md)

    if FURTHER_READING_MD.exists():
        further_reading_md = FURTHER_READING_MD.read_text(encoding="utf-8", errors="replace")
        emit(
            "further-reading/index.html",
            markdown_title(further_reading_md, "Further reading"),
            further_reading_md,
        )

    # Reader (legacy V1 single-page archive)
    if chapter_pages:
        reader_parts = [
            "# Reader / V1 / source-grounded thesis",
            "",
            "The earlier long-form, chapter-by-chapter walkthrough remains here as the archive destination.",
            "",
            "## Table of contents",
            "",
        ]
        for anchor_id, title, _src_path, _h1 in chapter_pages:
            reader_parts.append(f"- [{title}](#{anchor_id})")
        reader_parts.append("")
        reader_md = "\n".join(reader_parts) + "\n\n---\n\n" + "\n\n---\n\n".join(
            [Path(src_path).read_text(encoding="utf-8", errors="replace").rstrip() for _anchor_id, _title, src_path, _h1 in chapter_pages]
        )
        _html_body, reader_text = emit_markdown_page(
            out_dir=out_dir,
            template=template,
            sources=sources,
            href="reader/index.html",
            title="Reader / V1",
            md=reader_md,
            page_kind="",
            base_url=base_url,
            og_image_url=og_image_url,
            nav_html=nav_for("reader/index.html"),
        )
        page_hrefs.append("reader/index.html")
        search_index.append({"href": "reader/index.html", "title": "Reader / V1", "text": reader_text})

        for anchor_id, title, src_path, _h1 in chapter_pages:
            md = Path(src_path).read_text(encoding="utf-8", errors="replace")
            _html_body, text_body = blocks_to_html(parse_blocks(md), sources, root=page_root("reader/index.html"))
            search_index.append({"href": f"reader/index.html#{anchor_id}", "title": title, "text": text_body})

    (out_dir / "search_index.json").write_text(json.dumps(search_index, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    write_sitemap(out_dir, base_url, page_hrefs)
    write_robots(out_dir, base_url)

    print(f"wrote site to {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
