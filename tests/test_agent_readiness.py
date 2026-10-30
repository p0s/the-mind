from __future__ import annotations

import re
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import build_site  # noqa: E402

BASE_URL = "https://the-mind.xyz/"


class ReadingBody(HTMLParser):
    """Collect block text and link targets from the rendered page body, without citation widgets."""

    BLOCKS = {"p", "li", "h1", "h2", "h3", "h4", "h5", "h6"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.depth = 0
        self.skip = 0
        self.blocks: list[str] = []
        self.current: list[str] | None = None
        self.targets: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {name: value or "" for name, value in attrs}
        if not self.depth:
            if tag == "div" and values.get("class") == "reading-body":
                self.depth = 1
            return
        if tag == "div":
            self.depth += 1
        for name in ("href", "src"):
            if values.get(name):
                self.targets.append(values[name])
        if tag == "span" and (self.skip or "cite_ref" in values.get("class", "").split()):
            self.skip += 1
        if tag in self.BLOCKS:
            self.current = []
        if tag == "br" and self.current is not None:
            self.current.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if not self.depth:
            return
        if tag == "div":
            self.depth -= 1
        if tag == "span" and self.skip:
            self.skip -= 1
        if tag in self.BLOCKS and self.current is not None:
            text = " ".join("".join(self.current).split())
            if text:
                self.blocks.append(text)
            self.current = None

    def handle_data(self, data: str) -> None:
        if self.depth and not self.skip and self.current is not None:
            self.current.append(data)


def markdown_plain_text(markdown: str) -> str:
    text = re.sub(r"!\[([^\]]*)\]\([^)]+\)", r"\1", markdown)
    text = re.sub(r"\[((?:\\.|[^\]\\])+)\]\([^)]+\)", r"\1", text)
    text = text.replace("**", "")
    text = re.sub(r"(?<!\w)\*([^*\n]+?)\*(?!\w)", r"\1", text)
    text = re.sub(r"(?<!\w)_([^_\n]+?)_(?!\w)", r"\1", text)
    text = re.sub(r"(?m)^(?:#{1,6}|>|-|\d+\.)\s+", "", text)
    return " ".join(text.split())


def canonical_target(page_url: str, href: str) -> str:
    target = urljoin(page_url, href)
    parts = urlsplit(target)
    if parts.path.endswith("/index.html"):
        target = target.replace(parts.path, parts.path[: -len("index.html")], 1)
    return target


class TestAgentReadiness(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary = tempfile.TemporaryDirectory(prefix="the-mind-agents-")
        cls.dist = Path(cls.temporary.name) / "dist"
        build_site.main(["--out", str(cls.dist)])
        sitemap = ET.parse(cls.dist / "sitemap.xml").getroot()
        cls.page_urls = [(node.text or "").strip() for node in sitemap.iter() if node.tag.endswith("loc")]

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary.cleanup()

    def test_robots_declares_content_signals_without_a_training_preference(self) -> None:
        robots = (self.dist / "robots.txt").read_text(encoding="utf-8")
        directives = [line for line in robots.splitlines() if line and not line.startswith("#")]
        self.assertEqual(
            directives,
            [
                "User-agent: *",
                "Content-Signal: search=yes, ai-input=yes",
                "Disallow:",
                "Sitemap: https://the-mind.xyz/sitemap.xml",
            ],
        )
        self.assertNotIn("ai-train=", robots)
        self.assertTrue(robots.isascii())

    def test_every_page_has_a_faithful_markdown_alternate(self) -> None:
        self.assertEqual(len(self.page_urls), 18)
        for page_url in self.page_urls:
            rel = page_url[len(BASE_URL):]
            with self.subTest(page=rel or "/"):
                html = (self.dist / rel / "index.html").read_text(encoding="utf-8")
                markdown = (self.dist / rel / "index.md").read_text(encoding="utf-8")
                self.assertIn('<link rel="alternate" type="text/markdown" href="index.md" />', html)
                self.assertTrue(markdown.startswith('---\ntitle: "'))
                self.assertIn(f'\ncanonical_url: "{page_url}"\n---\n', markdown)
                self.assertIn(build_site.MARKDOWN_FOOTER_TEXT, markdown)
                self.assertNotRegex(markdown, r"<(?:!--|[a-z]+[\s>/])")
                self.assertNotRegex(markdown, r"\]\((?!https?://|mailto:)")

                body = ReadingBody()
                body.feed(html)
                self.assertTrue(body.blocks)
                plain = markdown_plain_text(markdown)
                for block in body.blocks:
                    self.assertIn(block, plain)
                for href in body.targets:
                    self.assertIn(canonical_target(page_url, href), markdown)

    def test_markdown_citations_keep_locators_and_source_details(self) -> None:
        markdown = (self.dist / "questions/what-is-a-mind/index.md").read_text(encoding="utf-8")
        self.assertIn(
            "([Talk: Self Models of Loving Grace, 32:16](https://media.ccc.de/v/38c3-self-models-of-loving-grace?t=1936))",
            markdown,
        )
        self.assertIn(
            "- [The Machine Consciousness Hypothesis](https://cimc.ai/cimcHypothesis.pdf) — "
            "Primary source · Paper · Joscha Bach, Hikari Sorensen · 2026-01-16",
            markdown,
        )
        claims = (self.dist / "claims/index.md").read_text(encoding="utf-8")
        self.assertIn("## [CLM-0001](https://the-mind.xyz/claims/#clm-0001)", claims)
        self.assertIn("Basis: **Project synthesis**", claims)
        reader = (self.dist / "reader/index.md").read_text(encoding="utf-8")
        self.assertRegex(reader, r"(?m)^\[(?:BACH|SYNTH|NOTE|OPEN)\] ")
        self.assertNotIn("```mermaid", reader)

    def test_llms_txt_lists_every_markdown_page(self) -> None:
        llms = (self.dist / "llms.txt").read_text(encoding="utf-8")
        self.assertTrue(llms.startswith(f"# the-mind\n\n> {build_site.page_description('index.html')}\n"))
        self.assertIn("Not affiliated with or endorsed by Joscha Bach.", llms)
        self.assertIn("## Optional", llms)
        for page_url in self.page_urls:
            href = page_url[len(BASE_URL):] + "index.html"
            self.assertIn(f"]({page_url}index.md): {build_site.page_description(href)}\n", llms)

    def test_markdown_links_resolve_like_the_html(self) -> None:
        page = "https://the-mind.xyz/guide/"
        resolve = lambda href: build_site.markdown_site_url(href, base_url=BASE_URL, page_url=page)  # noqa: E731
        self.assertEqual(resolve("/questions/what-is-a-mind/"), "https://the-mind.xyz/questions/what-is-a-mind/")
        self.assertEqual(resolve("/guide"), "https://the-mind.xyz/guide/")
        self.assertEqual(resolve("glossary/index.html#term"), "https://the-mind.xyz/glossary/#term")
        self.assertEqual(resolve("#section"), "https://the-mind.xyz/guide/#section")
        self.assertEqual(resolve("../claims/"), "https://the-mind.xyz/claims/")
        self.assertEqual(resolve("/assets/og.png"), "https://the-mind.xyz/assets/og.png")
        self.assertEqual(resolve("https://example.org/a_(b)"), "https://example.org/a_(b)")
        inline = build_site.markdown_inline(
            "See CLM-0002, `CLM-0003`, and [the guide](/guide/).", base_url=BASE_URL, page_url=page
        )
        self.assertEqual(
            inline,
            "See [CLM-0002](https://the-mind.xyz/claims/#clm-0002), `CLM-0003`, and "
            "[the guide](https://the-mind.xyz/guide/).",
        )
        self.assertEqual(build_site.markdown_link_text("A [draft] title"), "A \\[draft\\] title")
        self.assertEqual(build_site.markdown_destination("https://example.org/a b"), "<https://example.org/a%20b>")


if __name__ == "__main__":
    unittest.main()
