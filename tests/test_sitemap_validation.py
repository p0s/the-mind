from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import build_site  # noqa: E402


BASE_URL = "https://the-mind.xyz/"


class TestSitemapValidation(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="the-mind-sitemap-")
        self.addCleanup(self.temporary.cleanup)
        self.out_dir = Path(self.temporary.name) / "dist"
        self.out_dir.mkdir()
        self.write_page("index.html", "https://the-mind.xyz/")
        self.write_page("about/index.html", "https://the-mind.xyz/about/")
        build_site.write_sitemap(self.out_dir, BASE_URL, ["index.html", "about/index.html"])
        build_site.write_robots(self.out_dir, BASE_URL)

    def write_page(self, relative: str, canonical: str, head_extra: str = "") -> Path:
        page = self.out_dir / relative
        page.parent.mkdir(parents=True, exist_ok=True)
        page.write_text(
            f'<!doctype html><html><head>{head_extra}<link rel="canonical" href="{canonical}" /></head><body></body></html>',
            encoding="utf-8",
        )
        return page

    def test_sitemap_exactly_covers_rendered_canonical_pages(self) -> None:
        self.assertEqual(build_site.validate_sitemap_output(self.out_dir, BASE_URL), {"pages": 2, "sitemaps": 1})

    def test_missing_rendered_page_fails_the_build(self) -> None:
        build_site.write_sitemap(self.out_dir, BASE_URL, ["index.html"])
        with self.assertRaisesRegex(ValueError, "missing indexable pages: https://the-mind.xyz/about/"):
            build_site.validate_sitemap_output(self.out_dir, BASE_URL)

    def test_noindex_page_cannot_be_listed(self) -> None:
        self.write_page("about/index.html", "https://the-mind.xyz/about/", '<meta name="robots" content="noindex,follow" />')
        with self.assertRaisesRegex(ValueError, "includes a noindex page"):
            build_site.validate_sitemap_output(self.out_dir, BASE_URL)

    def test_meta_refresh_redirect_cannot_be_listed(self) -> None:
        self.write_page("legacy/index.html", "https://the-mind.xyz/legacy/", '<meta http-equiv="refresh" content="0; url=/about/" />')
        build_site.write_sitemap(self.out_dir, BASE_URL, ["index.html", "about/index.html", "legacy/index.html"])
        with self.assertRaisesRegex(ValueError, "includes a redirect page"):
            build_site.validate_sitemap_output(self.out_dir, BASE_URL)

    def test_cloudflare_redirect_cannot_be_listed(self) -> None:
        (self.out_dir / "_redirects").write_text("/about/ /guide/ 301\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "includes a redirect route"):
            build_site.validate_sitemap_output(self.out_dir, BASE_URL)

    def test_noncanonical_host_fails_the_build(self) -> None:
        self.write_page("about/index.html", "https://www.the-mind.xyz/about/")
        with self.assertRaisesRegex(ValueError, "canonical HTTPS host the-mind.xyz"):
            build_site.validate_sitemap_output(self.out_dir, BASE_URL)

    def test_question_drafts_are_not_rendered_or_added_to_the_sitemap(self) -> None:
        questions = Path(self.temporary.name) / "questions"
        questions.mkdir()
        (questions / "published.md").write_text("# Published question\n", encoding="utf-8")
        (questions / "draft.md").write_text("---\ndraft: true\n---\n# Draft question\n", encoding="utf-8")
        output = Path(self.temporary.name) / "site"

        existing_description = build_site.page_description
        def description(href):
            if href == "questions/published/index.html":
                return "Published question used to check sitemap draft filtering."
            return existing_description(href)
        with patch.object(build_site, "QUESTIONS_DIR", questions), patch.object(build_site, "page_description", side_effect=description):
            self.assertEqual(build_site.main(["--out", str(output)]), 0)

        self.assertTrue((output / "questions/published/index.html").is_file())
        self.assertFalse((output / "questions/draft/index.html").exists())
        sitemap = (output / "sitemap.xml").read_text(encoding="utf-8")
        self.assertIn("https://the-mind.xyz/questions/published/", sitemap)
        self.assertNotIn("https://the-mind.xyz/questions/draft/", sitemap)


if __name__ == "__main__":
    unittest.main()
