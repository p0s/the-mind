import json
import os
import re
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


import build_site  # noqa: E402
from _core.seo import PAGE_SEO  # noqa: E402


class HeadParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.metadata: dict[str, str] = {}
        self.canonical = ""
        self.title_parts: list[str] = []
        self.json_ld_parts: list[str] = []
        self._in_title = False
        self._in_json_ld = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {name: value or "" for name, value in attrs}
        if tag == "meta":
            key = values.get("name") or values.get("property")
            if key:
                self.metadata[key] = values.get("content", "")
        elif tag == "link" and values.get("rel") == "canonical":
            self.canonical = values.get("href", "")
        elif tag == "title":
            self._in_title = True
        elif tag == "script" and values.get("type") == "application/ld+json":
            self._in_json_ld = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False
        elif tag == "script" and self._in_json_ld:
            self._in_json_ld = False

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title_parts.append(data)
        if self._in_json_ld:
            self.json_ld_parts.append(data)

    @property
    def title(self) -> str:
        return "".join(self.title_parts).strip()

    @property
    def json_ld(self) -> dict[str, object]:
        return json.loads("".join(self.json_ld_parts))


class TestSiteSEO(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory()
        cls.dist = Path(cls._tmp.name) / "dist"
        with patch.dict(os.environ, {"THE_MIND_SITE_BASE_URL": ""}):
            result = build_site.main(["--out", str(cls.dist)])
        if result != 0:
            raise RuntimeError(f"site build failed with exit {result}")

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    def parse(self, href: str) -> HeadParser:
        parser = HeadParser()
        parser.feed((self.dist / href).read_text(encoding="utf-8"))
        parser.close()
        return parser

    def test_metadata_contract_covers_every_public_route(self) -> None:
        question_routes = {
            f"questions/{path.stem}/index.html"
            for path in (ROOT / "content" / "questions").glob("*.md")
            if path.name != "index.md"
        }
        expected = {
            "index.html",
            "guide/index.html",
            "questions/index.html",
            "archive/index.html",
            "glossary/index.html",
            "claims/index.html",
            "sources/index.html",
            "further-reading/index.html",
            "reader/index.html",
        } | question_routes
        self.assertEqual(set(PAGE_SEO), expected)
        self.assertEqual(len({meta.title for meta in PAGE_SEO.values()}), len(PAGE_SEO))
        self.assertEqual(len({meta.description for meta in PAGE_SEO.values()}), len(PAGE_SEO))
        for meta in PAGE_SEO.values():
            self.assertGreaterEqual(len(meta.description), 90)
            self.assertLessEqual(len(meta.description), 165)
            self.assertLessEqual(len(meta.title), 65)

    def test_every_route_has_matching_canonical_social_and_schema_metadata(self) -> None:
        for href, seo in PAGE_SEO.items():
            with self.subTest(href=href):
                parsed = self.parse(href)
                html = (self.dist / href).read_text(encoding="utf-8")
                page_url = build_site.absolute_page_url(build_site.DEFAULT_SITE_BASE_URL, href)
                self.assertEqual(len(re.findall(r"<h1\b", html)), 1)
                self.assertNotRegex(html, r"\{\{[a-z_]+\}\}")
                self.assertEqual(parsed.title, seo.title)
                self.assertEqual(parsed.metadata["description"], seo.description)
                self.assertEqual(parsed.metadata["robots"], "index,follow,max-image-preview:large")
                self.assertEqual(parsed.canonical, page_url)
                self.assertEqual(parsed.metadata["og:title"], seo.title)
                self.assertEqual(parsed.metadata["og:description"], seo.description)
                self.assertEqual(parsed.metadata["og:url"], page_url)
                self.assertEqual(parsed.metadata["twitter:title"], seo.title)
                self.assertEqual(parsed.metadata["twitter:description"], seo.description)

                graph = parsed.json_ld["@graph"]
                website = next(item for item in graph if item["@type"] == "WebSite")
                suffix = "article" if seo.schema_type == "Article" else "webpage"
                page = next(item for item in graph if item.get("@id") == f"{page_url}#{suffix}")
                self.assertEqual(website["url"], build_site.DEFAULT_SITE_BASE_URL)
                self.assertEqual(page["@type"], seo.schema_type)
                self.assertEqual(page["description"], seo.description)
                if seo.schema_type == "Article":
                    self.assertEqual(page["mainEntityOfPage"], {"@type": "WebPage", "@id": page_url})

    def test_question_breadcrumbs_and_item_list_are_visible_and_consistent(self) -> None:
        question_href = "questions/could-ai-be-conscious/index.html"
        html = (self.dist / question_href).read_text(encoding="utf-8")
        self.assertRegex(
            html,
            re.compile(
                r'<nav class="breadcrumbs" aria-label="Breadcrumb"><ol>.*Home.*Questions.*Could AI be conscious\?',
                re.DOTALL,
            ),
        )

        question_page = self.parse(question_href).json_ld["@graph"]
        breadcrumb = next(item for item in question_page if item["@type"] == "BreadcrumbList")
        self.assertEqual(
            [item["item"] for item in breadcrumb["itemListElement"]],
            [
                "https://the-mind.xyz/",
                "https://the-mind.xyz/questions/",
                "https://the-mind.xyz/questions/could-ai-be-conscious/",
            ],
        )

        hub = self.parse("questions/index.html").json_ld["@graph"]
        hub_page = next(item for item in hub if item.get("@id") == "https://the-mind.xyz/questions/#webpage")
        item_list = hub_page["mainEntity"]
        self.assertEqual(item_list["@type"], "ItemList")
        self.assertEqual(item_list["numberOfItems"], 8)
        self.assertEqual(len(item_list["itemListElement"]), 8)
        self.assertEqual(
            [item["url"] for item in item_list["itemListElement"]],
            [
                "https://the-mind.xyz/questions/what-is-a-mind/",
                "https://the-mind.xyz/questions/why-do-feelings-matter/",
                "https://the-mind.xyz/questions/what-is-the-self/",
                "https://the-mind.xyz/questions/is-free-will-real/",
                "https://the-mind.xyz/questions/what-is-consciousness/",
                "https://the-mind.xyz/questions/could-ai-be-conscious/",
                "https://the-mind.xyz/questions/do-llms-have-qualia/",
                "https://the-mind.xyz/questions/does-this-kill-spirituality/",
            ],
        )

    def test_article_schema_mirrors_existing_source_anchors(self) -> None:
        graph = self.parse("questions/could-ai-be-conscious/index.html").json_ld["@graph"]
        article = next(item for item in graph if item["@type"] == "Article")
        citations = article["citation"]
        self.assertTrue(any(url.startswith("https://cimc.ai/cimcHypothesis.pdf#page=") for url in citations))
        self.assertEqual(len(citations), len(set(citations)))

    def test_reader_nests_chapter_headings_below_one_page_heading(self) -> None:
        html = (self.dist / "reader/index.html").read_text(encoding="utf-8")
        self.assertEqual(len(re.findall(r"<h1\b", html)), 1)
        self.assertIn(
            '<h2 id="chapter-1-the-project-mind-as-a-mechanism">Chapter 1: The Project (Mind as a Mechanism)</h2>',
            html,
        )

    def test_sitemap_and_robots_use_only_canonical_indexable_routes(self) -> None:
        root = ET.parse(self.dist / "sitemap.xml").getroot()
        namespace = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
        observed = {item.text for item in root.findall("sm:url/sm:loc", namespace)}
        expected = {
            build_site.absolute_page_url(build_site.DEFAULT_SITE_BASE_URL, href)
            for href, seo in PAGE_SEO.items()
            if seo.indexable
        }
        self.assertEqual(observed, expected)
        self.assertEqual(
            (self.dist / "robots.txt").read_text(encoding="utf-8"),
            "User-agent: *\nAllow: /\n\nSitemap: https://the-mind.xyz/sitemap.xml\n",
        )

    def test_site_base_url_accepts_clean_subpaths_and_rejects_ambiguous_values(self) -> None:
        with patch.dict(os.environ, {"THE_MIND_SITE_BASE_URL": "https://preview.example/site"}):
            self.assertEqual(build_site.site_base_url(), "https://preview.example/site/")
        for value in ("preview.example", "https://preview.example/?draft=1", "https://user@preview.example/"):
            with self.subTest(value=value), patch.dict(os.environ, {"THE_MIND_SITE_BASE_URL": value}):
                with self.assertRaises(ValueError):
                    build_site.site_base_url()


if __name__ == "__main__":
    unittest.main()
