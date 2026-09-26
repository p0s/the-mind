import json
import subprocess
import sys
import unittest
from html.parser import HTMLParser
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import build_site  # noqa: E402


class Links(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.hrefs = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.hrefs.append(dict(attrs)["href"])


class TestCitations(unittest.TestCase):
    def setUp(self):
        self.sources = {
            "web_cimc_ai_cimchypothesis_pdf": {
                "url": "https://cimc.ai/cimcHypothesis.pdf",
                "title": "The Machine Consciousness Hypothesis",
                "creator_or_channel": "Joscha Bach, Hikari Sorensen",
                "published_date": "2026-01-16",
                "kind": "web",
            },
            "yt_example": {"url": "https://www.youtube.com/watch?v=example", "title": "A talk", "kind": "youtube"},
        }
        self.md = (
            "A claim. <!-- src: web_cimc_ai_cimchypothesis_pdf @ p6; "
            "web_cimc_ai_cimchypothesis_pdf @ p12-13; web_cimc_ai_cimchypothesis_pdf @ p6 -->\n\n"
            "- Another claim. <!-- src: yt_example @ 01:32:16 -->\n"
        )

    def render(self):
        return build_site.blocks_to_html(build_site.parse_blocks(self.md), self.sources, root="./")[0]

    def test_group_preserves_every_distinct_location_and_printed_page_labels(self):
        html = self.render()
        hrefs = Links(html).hrefs
        self.assertIn("https://cimc.ai/cimcHypothesis.pdf#page=7", hrefs)
        self.assertIn("https://cimc.ai/cimcHypothesis.pdf#page=13", hrefs)
        self.assertIn("https://www.youtube.com/watch?v=example&t=5536s", hrefs)
        self.assertIn("p. 6 +1", html)
        self.assertIn("pp. 12–13", html)
        self.assertIn("01:32:16", html)
        self.assertNotIn("+2", html)

    def test_metadata_is_escaped_and_source_lists_keep_full_titles(self):
        self.sources["yt_example"]["title"] = '<script>alert("title")</script>'
        self.sources["yt_example"]["creator_or_channel"] = '<img src=x onerror="oops">'
        html = self.render()
        self.assertNotIn("<script>", html)
        self.assertNotIn("<img", html)
        self.assertIn("&lt;script&gt;", html)
        source_list, _ = build_site.blocks_to_html(
            build_site.parse_blocks("## Sources\n\n- yt_example @ 00:32:16\n"), self.sources, root="./"
        )
        self.assertIn("&lt;script&gt;", source_list)
        self.assertNotIn("data-source=", source_list)

    def test_browser_layout_preference_and_no_popover_fallback(self):
        result = subprocess.run(
            ["node", str(ROOT / "tests" / "citations_ui.cjs")],
            input=json.dumps({"html": self.render()}),
            text=True, capture_output=True, cwd=ROOT,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {"passed": 5})


if __name__ == "__main__":
    unittest.main()
