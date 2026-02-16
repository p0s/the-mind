#!/usr/bin/env python3
"""
Build a static site from the manuscript + knowledge base.

Outputs to ./dist/ (gitignored). No transcript text is read or emitted.
Optionally, local diarization metadata may be read to enrich cite tooltips.

Pages:
- index.html
- blog/ (one page per blog post + an index)
- reader/ (single-page view of the whole book)
- glossary/
- claims/
- sources/

The site keeps provenance as *links to original sources* (URL + timecode).
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
BLOG_ROOT_DIR = ROOT / "content" / "blog"
BLOG_INDEX_MD = BLOG_ROOT_DIR / "index.md"
BLOG_POSTS_DIR = BLOG_ROOT_DIR / "posts"
GLOSSARY_MD = ROOT / "notes" / "glossary.md"
CLAIMS_MD = ROOT / "notes" / "claims.md"
LINEAGE_MD = ROOT / "notes" / "lineage.md"
SOURCES_CSV = ROOT / "sources" / "sources.csv"
SPEAKERS_DIR = ROOT / "transcripts" / "_speakers"
DEFAULT_SITE_BASE_URL = "https://the-mind.xyz/"


TAG_RX = re.compile(r"^\[(BACH|SYNTH|NOTE|OPEN)\]\s*", re.IGNORECASE)
SRC_RX = re.compile(
    r"<!--\s*src:\s*([a-z0-9_\\-]+)\s*@\s*(\d{2}:\d{2}:\d{2}(?:[\\.,]\d{1,3})?)\s*-->",
    re.IGNORECASE,
)
SRC_ITEM_RX = re.compile(r"^([a-z0-9_\-]+)\s+@\s+(\d{2}:\d{2}:\d{2}(?:[\\.,]\d{1,3})?)\b(.*)$", re.IGNORECASE)


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


def render_cite_link(source_id: str, timecode: str, sources: Dict[str, Dict[str, str]], *, show_time: bool) -> Optional[str]:
    meta = sources.get(source_id, {})
    url = (meta.get("url") or "").strip()
    if not url:
        return None

    tc = (timecode or "").strip().replace(",", ".")
    href = timecoded_url(url, tc)

    fmt = infer_presentation_format(meta)
    title = re.sub(r"\s+", " ", (meta.get("title") or "").strip()) or source_id
    label = f"{fmt}: {title}"

    tooltip_lines = [f"{fmt}: {title}", f"{source_id} @ {tc}"]
    bach_s = bach_time_seconds(source_id)
    if bach_s is not None:
        tooltip_lines.append(f"Bach time: {seconds_to_hhmmss(bach_s)} (approx)")
    tooltip = " | ".join(tooltip_lines)

    a = (
        f'<a class="cite" href="{escape_attr(href)}" target="_blank" rel="noopener noreferrer" title="{escape_attr(tooltip)}">{escape(label)}</a>'
    )
    if show_time:
        return a + f'<span class="cite_time"> @ {escape(tc)}</span>'
    return a


def linkify_source_ref(text: str, sources: Dict[str, Dict[str, str]]) -> Optional[str]:
    """
    Turn "source_id @ HH:MM:SS ..." into a link to the canonical URL (+ timecode).

    This is primarily for "Anchors (sources + timecodes)" lists, but it also
    helps on glossary/claims pages where we cite with the same syntax.
    """
    m = SRC_ITEM_RX.match(text.strip())
    if not m:
        return None
    sid, tc, rest = m.groups()
    linked = render_cite_link(sid, tc, sources, show_time=True)
    if not linked:
        return None
    # Keep any trailing details (e.g. "(keywords: ...)") readable and searchable.
    tail = inline_format(rest) if rest else ""
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


def inline_format(s: str) -> str:
    # Conservative inline formatting: code, then links, then bold + italics.
    s = escape(s)
    # `code`
    def repl_code(m: re.Match[str]) -> str:
        # `s` is already escaped; prevent later emphasis regex from touching code.
        code = m.group(1).replace("*", "&#42;").replace("_", "&#95;")
        return f"<code>{code}</code>"

    s = re.sub(r"`([^`]+)`", repl_code, s)
    # [text](url)
    def repl_link(m: re.Match[str]) -> str:
        label = m.group(1)
        href = m.group(2)
        # `href` is already escaped except for quotes (escape() uses quote=False).
        href_attr = href.replace('"', "&quot;").replace("'", "&#x27;")
        if href.startswith(("http://", "https://")):
            return f'<a href="{href_attr}" target="_blank" rel="noopener noreferrer">{label}</a>'
        return f'<a href="{href_attr}">{label}</a>'

    s = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", repl_link, s)
    # **bold**
    s = re.sub(r"\*\*([^*]+)\*\*", lambda m: f"<strong>{m.group(1)}</strong>", s)
    # *italics* and _italics_ (keep conservative boundaries)
    s = re.sub(r"(?<!\w)\*([^*\n]+?)\*(?!\w)", lambda m: f"<em>{m.group(1)}</em>", s)
    s = re.sub(r"(?<!\w)_([^_\n]+?)_(?!\w)", lambda m: f"<em>{m.group(1)}</em>", s)
    return s


def strip_md_for_search(s: str) -> str:
    s = TAG_RX.sub("", s)
    s = SRC_RX.sub("", s)
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
    anchor: Optional[Tuple[str, str]] = None  # (source_id, timecode)


def parse_blocks(md: str) -> List[Block]:
    lines = md.splitlines()
    blocks: List[Block] = []

    in_code = False
    code_lang = ""
    code_lines: List[str] = []

    pending_tag: str = ""
    pending_anchor: Optional[Tuple[str, str]] = None

    cur_para: List[str] = []
    cur_list: List[str] = []
    cur_list_ordered = False
    cur_quote: List[str] = []

    def flush_para() -> None:
        nonlocal cur_para, pending_tag, pending_anchor
        if not cur_para:
            return
        text = " ".join([p.strip() for p in cur_para]).strip()
        tag = pending_tag
        anchor = pending_anchor
        pending_tag = ""
        pending_anchor = None

        # Extract inline anchor if present.
        m = SRC_RX.search(text)
        if m:
            anchor = (m.group(1), m.group(2).replace(",", "."))
            text = SRC_RX.sub("", text).strip()

        blocks.append(Block(kind="para", tag=tag, text=text, anchor=anchor))
        cur_para = []

    def flush_list() -> None:
        nonlocal cur_list, cur_list_ordered, pending_tag, pending_anchor
        if not cur_list:
            return
        tag = pending_tag
        anchor = pending_anchor
        pending_tag = ""
        pending_anchor = None
        blocks.append(
            Block(
                kind="list",
                tag=tag,
                text="",
                ordered=cur_list_ordered,
                items=cur_list[:],
                anchor=anchor,
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
            m2 = SRC_RX.search(rest)
            if m2:
                pending_anchor = (m2.group(1), m2.group(2).replace(",", "."))
                rest = SRC_RX.sub("", rest).strip()
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


def blocks_to_html(blocks: List[Block], sources: Dict[str, Dict[str, str]], *, root: str) -> Tuple[str, str]:
    parts: List[str] = []
    search_parts: List[str] = []
    seen_ids: Dict[str, int] = {}

    for b in blocks:
        if b.kind == "heading":
            txt = inline_format(b.text)
            base = slugify(b.text)
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
            lines = [ln for ln in b.text.split("\n")]
            inner = "<br />".join([inline_format(ln) for ln in lines])
            parts.append(f"<blockquote><p>{inner}</p></blockquote>")
            search_parts.append(strip_md_for_search(b.text))
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
                linked = linkify_source_ref(it, sources)
                parts.append(f"<li>{linked or inline_format(it)}</li>")
                search_parts.append(strip_md_for_search(it))
            parts.append(f"</{tag_list}>")
            if b.anchor:
                sid, tc = b.anchor
                rendered = render_cite_link(sid, tc, sources, show_time=False)
                if rendered:
                    parts.append(rendered)
            if b.tag:
                parts.append(wrap_close)
            continue
        if b.kind == "para":
            tag_attr = f' data-tag="{b.tag}"' if b.tag else ""
            wrap_open = f'<div class="blk"{tag_attr}>' if b.tag else ""
            wrap_close = "</div>" if b.tag else ""
            if b.tag:
                parts.append(wrap_open + f'<span class="pill">{escape(b.tag)}</span>')
            txt = inline_format(b.text)
            cite_html = ""
            if b.anchor:
                sid, tc = b.anchor
                rendered = render_cite_link(sid, tc, sources, show_time=False)
                if rendered:
                    cite_html = " " + rendered
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


def absolute_page_url(base_url: str, href: str) -> str:
    return urljoin(base_url, href.lstrip("./"))


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
        .replace("{{body_class}}", "")
        .replace("{{extra_scripts}}", extra_scripts)
    )


def build_nav(chapters: List[Tuple[str, str]], *, current_href: str, root: str) -> str:
    # chapters: (anchor_id, title)
    def is_current(href: str) -> bool:
        if href == current_href:
            return True
        if href == "blog/index.html" and current_href.startswith("blog/"):
            return True
        return False

    def a(href: str, label: str) -> str:
        cur = ' aria-current="page"' if is_current(href) else ""
        return f'<a href="{escape(root + href)}"{cur}>{escape(label)}</a>'

    parts: List[str] = []
    parts.append('<div class="nav">')
    parts.append('<div class="navgroup">')
    parts.append('<div class="navtitle">Core</div>')
    parts.append(a("index.html", "Home"))
    parts.append(a("reader/index.html", "Reader"))
    parts.append(a("blog/index.html", "Blog"))
    kb_open = current_href.startswith(("glossary/", "claims/", "sources/", "lineage/"))
    parts.append(f'<details class="navdetails"{" open" if kb_open else ""}>')
    parts.append('<summary class="navsummary">Knowledge base</summary>')
    parts.append(a("glossary/index.html", "Glossary"))
    parts.append(a("claims/index.html", "Claims"))
    parts.append(a("sources/index.html", "Sources"))
    parts.append(a("lineage/index.html", "Lineage"))
    parts.append("</details>")
    parts.append("</div>")

    parts.append('<div class="navgroup">')
    parts.append('<div class="navtitle">Book</div>')
    for anchor_id, t in chapters:
        parts.append(a(f"reader/index.html#{anchor_id}", t))
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

    chapters_for_nav = [(anchor_id, title) for anchor_id, title, _src, _h1 in chapter_pages]

    search_index: List[Dict[str, str]] = []

    # Home (canonical source lives in site/home.md)
    if HOME_MD.exists():
        home_md = HOME_MD.read_text(encoding="utf-8", errors="replace")
    else:
        home_md = "# the-mind\n\n_Home content missing: site/home.md._\n"
    home_html, home_text = blocks_to_html(parse_blocks(home_md), sources, root="./")
    home_nav = build_nav(chapters_for_nav, current_href="index.html", root="./")
    write(
        out_dir / "index.html",
        render_page(
            template,
            title="the-mind",
            nav=home_nav,
            content=home_html,
            root="./",
            page_id="home",
            page_url=absolute_page_url(base_url, "index.html"),
            og_image_url=og_image_url,
        ),
    )
    search_index.append({"href": "index.html", "title": "Home", "text": home_text})

    # Reader (single page)
    reader_parts = ["# Reader", "", "A single-page view of the whole book.", "", "## Table of contents", ""]
    for anchor_id, title, _src_path, _h1 in chapter_pages:
        reader_parts.append(f"- [{title}](#{anchor_id})")
    reader_parts.append("")
    reader_md = "\n".join(reader_parts) + "\n\n---\n\n" + "\n\n---\n\n".join(
        [Path(src_path).read_text(encoding="utf-8", errors="replace").rstrip() for _anchor_id, _title, src_path, _h1 in chapter_pages]
    )

    reader_html, reader_text = blocks_to_html(parse_blocks(reader_md), sources, root="../")
    nav = build_nav(chapters_for_nav, current_href="reader/index.html", root="../")
    write(
        out_dir / "reader" / "index.html",
        render_page(
            template,
            title="Reader",
            nav=nav,
            content=reader_html,
            root="../",
            page_id="reader",
            page_url=absolute_page_url(base_url, "reader/index.html"),
            og_image_url=og_image_url,
        ),
    )
    search_index.append({"href": "reader/index.html", "title": "Reader", "text": reader_text})

    # Blog index + pages
    blog_files: List[Path] = []
    if BLOG_POSTS_DIR.exists():
        blog_files = sorted([p for p in BLOG_POSTS_DIR.glob("*.md") if p.is_file()])

    blog_pages: List[Tuple[str, str, str]] = []  # (href, title, src_path)
    for p in blog_files:
        md = p.read_text(encoding="utf-8", errors="replace")
        title_line = next((l[2:].strip() for l in md.splitlines() if l.startswith("# ")), p.stem)
        title = re.sub(r"\s+", " ", title_line).strip()
        href = f"blog/{p.stem}.html"
        blog_pages.append((href, title, str(p)))

    blog_index_parts: List[str] = []
    if BLOG_INDEX_MD.exists():
        blog_index_parts.extend(BLOG_INDEX_MD.read_text(encoding="utf-8", errors="replace").rstrip().splitlines())
    else:
        blog_index_parts.extend(["# Blog", "", "_Blog index missing._"])

    blog_index_parts.extend(["", "## Posts", ""])
    if blog_pages:
        for href, title, _src_path in blog_pages:
            blog_index_parts.append(f"- [{title}](./{Path(href).name})")
    else:
        blog_index_parts.append("_No posts yet._")

    blog_index_md = "\n".join(blog_index_parts) + "\n"
    blog_index_html, blog_index_text = blocks_to_html(parse_blocks(blog_index_md), sources, root="./")
    blog_nav = build_nav(chapters_for_nav, current_href="blog/index.html", root="../")
    write(
        out_dir / "blog" / "index.html",
        render_page(
            template,
            title="Blog",
            nav=blog_nav,
            content=blog_index_html,
            root="../",
            page_id="blog-index",
            page_url=absolute_page_url(base_url, "blog/index.html"),
            og_image_url=og_image_url,
        ),
    )
    search_index.append({"href": "blog/index.html", "title": "Blog", "text": blog_index_text})

    for href, title, src_path in blog_pages:
        md = Path(src_path).read_text(encoding="utf-8", errors="replace")
        html_body, text_body = blocks_to_html(parse_blocks(md), sources, root="../")
        nav = build_nav(chapters_for_nav, current_href=href, root="../")
        write(
            out_dir / href,
            render_page(
                template,
                title=title,
                nav=nav,
                content=html_body,
                root="../",
                page_id=href,
                page_url=absolute_page_url(base_url, href),
                og_image_url=og_image_url,
            ),
        )
        search_index.append({"href": href, "title": title, "text": text_body})

    # Per-chapter search results that jump into the Reader.
    for anchor_id, title, src_path, _h1 in chapter_pages:
        md = Path(src_path).read_text(encoding="utf-8", errors="replace")
        _html_body, text_body = blocks_to_html(parse_blocks(md), sources, root="../")
        search_index.append({"href": f"reader/index.html#{anchor_id}", "title": title, "text": text_body})

    # Glossary
    if GLOSSARY_MD.exists():
        md = GLOSSARY_MD.read_text(encoding="utf-8", errors="replace")
        html_body, text_body = blocks_to_html(parse_blocks(md), sources, root="../")
        nav = build_nav(chapters_for_nav, current_href="glossary/index.html", root="../")
        write(
            out_dir / "glossary" / "index.html",
            render_page(
                template,
                title="Glossary",
                nav=nav,
                content=html_body,
                root="../",
                page_id="glossary",
                page_url=absolute_page_url(base_url, "glossary/index.html"),
                og_image_url=og_image_url,
            ),
        )
        search_index.append({"href": "glossary/index.html", "title": "Glossary", "text": text_body})

    # Claims
    if CLAIMS_MD.exists():
        md = CLAIMS_MD.read_text(encoding="utf-8", errors="replace")
        html_body, text_body = blocks_to_html(parse_blocks(md), sources, root="../")
        nav = build_nav(chapters_for_nav, current_href="claims/index.html", root="../")
        write(
            out_dir / "claims" / "index.html",
            render_page(
                template,
                title="Claims",
                nav=nav,
                content=html_body,
                root="../",
                page_id="claims",
                page_url=absolute_page_url(base_url, "claims/index.html"),
                og_image_url=og_image_url,
            ),
        )
        search_index.append({"href": "claims/index.html", "title": "Claims", "text": text_body})

    # Lineage
    if LINEAGE_MD.exists():
        md = LINEAGE_MD.read_text(encoding="utf-8", errors="replace")
        html_body, text_body = blocks_to_html(parse_blocks(md), sources, root="../")
        nav = build_nav(chapters_for_nav, current_href="lineage/index.html", root="../")
        write(
            out_dir / "lineage" / "index.html",
            render_page(
                template,
                title="Lineage",
                nav=nav,
                content=html_body,
                root="../",
                page_id="lineage",
                page_url=absolute_page_url(base_url, "lineage/index.html"),
                og_image_url=og_image_url,
            ),
        )
        search_index.append({"href": "lineage/index.html", "title": "Lineage", "text": text_body})

    # Sources (keep-only)
    keep = []
    for sid, row in sources.items():
        notes = (row.get("notes") or "")
        if "curation_status=keep" in notes:
            keep.append((sid, row))
    keep.sort(key=lambda t: ((t[1].get("published_date") or ""), t[0]))

    src_lines = ["# Sources", "", "Keystone/kept sources referenced by the manuscript.", ""]
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
            head += f" — {url}"
        src_lines.append(head)
    src_md = "\n".join(src_lines) + "\n"

    src_html, src_text = blocks_to_html(parse_blocks(src_md), sources, root="../")
    nav = build_nav(chapters_for_nav, current_href="sources/index.html", root="../")
    write(
        out_dir / "sources" / "index.html",
        render_page(
            template,
            title="Sources",
            nav=nav,
            content=src_html,
            root="../",
            page_id="sources",
            page_url=absolute_page_url(base_url, "sources/index.html"),
            og_image_url=og_image_url,
        ),
    )
    search_index.append({"href": "sources/index.html", "title": "Sources", "text": src_text})

    (out_dir / "search_index.json").write_text(json.dumps(search_index, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")

    print(f"wrote site to {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
