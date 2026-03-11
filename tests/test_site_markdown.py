import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


import build_site  # noqa: E402


class TestSiteMarkdown(unittest.TestCase):
    def test_skips_chapter_keywords_comment(self) -> None:
        md = "\n".join(
            [
                "# Title",
                "",
                "<!-- chapter_keywords: a, b -->",
                "",
                "Hello",
                "",
            ]
        )
        blocks = build_site.parse_blocks(md)
        self.assertEqual([b.kind for b in blocks], ["heading", "para"])
        self.assertEqual(blocks[1].text, "Hello")

    def test_parses_bach_tag_and_multi_anchor(self) -> None:
        md = "[BACH] Hello <!-- src: yt_abc @ 00:01:02; ccc_def @ 00:03:04 | auto=needs_review -->\n"
        blocks = build_site.parse_blocks(md)
        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0].kind, "para")
        self.assertEqual(blocks[0].tag, "BACH")
        self.assertEqual(blocks[0].text, "Hello")
        self.assertEqual(blocks[0].anchors, [("yt_abc", "00:01:02"), ("ccc_def", "00:03:04")])

    def test_parses_pdf_page_locator_anchor(self) -> None:
        md = "[BACH] Hello <!-- src: web_x @ p16 -->\n"
        blocks = build_site.parse_blocks(md)
        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0].kind, "para")
        self.assertEqual(blocks[0].tag, "BACH")
        self.assertEqual(blocks[0].text, "Hello")
        self.assertEqual(blocks[0].anchor, ("web_x", "p16"))
        self.assertEqual(blocks[0].anchors, [("web_x", "p16")])

    def test_list_can_carry_anchor_from_tag_line(self) -> None:
        md = "\n".join(
            [
                "[BACH] <!-- src: yt_abc @ 00:01:02 -->",
                "- A",
                "- B",
                "",
            ]
        )
        blocks = build_site.parse_blocks(md)
        self.assertEqual([b.kind for b in blocks], ["list"])
        self.assertEqual(blocks[0].tag, "BACH")
        self.assertEqual(blocks[0].anchors, [("yt_abc", "00:01:02")])

    def test_linkifies_claim_and_term_ids(self) -> None:
        md = "See CLM-0001 and TERM-0002.\n"
        html_body, _text = build_site.blocks_to_html(build_site.parse_blocks(md), sources={}, root="./")
        self.assertIn('href="./claims/index.html#clm-0001"', html_body)
        self.assertIn('href="./glossary/index.html#term-0002"', html_body)

    def test_claims_have_deterministic_ids(self) -> None:
        md = "## CLM-0001: Foo\n\nBar\n"
        html_body, _text = build_site.blocks_to_html(
            build_site.parse_blocks(md),
            sources={},
            root="./",
            page_kind="claims",
        )
        self.assertIn('id="clm-0001"', html_body)

    def test_glossary_has_deterministic_ids(self) -> None:
        md = "\n".join(
            [
                "## Foo",
                "- Id: TERM-0001",
                "- Working meaning: ...",
                "",
                "## Bar",
                "- Id: TERM-0002",
                "",
            ]
        )
        html_body, _text = build_site.blocks_to_html(
            build_site.parse_blocks(md),
            sources={},
            root="./",
            page_kind="glossary",
        )
        self.assertIn('id="term-0001"', html_body)
        self.assertIn('id="term-0002"', html_body)

    def test_rewrites_site_root_links_relative_to_current_page(self) -> None:
        html_body, _text = build_site.blocks_to_html(
            build_site.parse_blocks("[Guide](/guide/) and [Mind](/questions/what-is-a-mind/)\n"),
            sources={},
            root="../../",
        )
        self.assertIn('href="../../guide/index.html"', html_body)
        self.assertIn('href="../../questions/what-is-a-mind/index.html"', html_body)

    def test_renders_markdown_images(self) -> None:
        html_body, _text = build_site.blocks_to_html(
            build_site.parse_blocks("![Chooser](/assets/reading-ai.svg)\n"),
            sources={},
            root="../",
        )
        self.assertIn('class="mdimg"', html_body)
        self.assertIn('src="../assets/reading-ai.svg"', html_body)

    def test_groups_same_source_citations_with_multiple_locators(self) -> None:
        md = "Hello <!-- src: web_x @ p16; web_x @ p18-19 -->\n"
        sources = {
            "web_x": {
                "url": "https://example.com/paper.pdf",
                "title": "Example Paper",
                "kind": "web",
                "notes": "format=essay",
            }
        }
        html_body, _text = build_site.blocks_to_html(build_site.parse_blocks(md), sources=sources, root="./")
        self.assertEqual(html_body.count('class="cite"'), 1)
        self.assertIn("@ p16, p18-19", html_body)

    def test_questions_nav_uses_section_link_in_summary(self) -> None:
        nav = build_site.build_nav(
            [("questions/what-is-a-mind/index.html", "What is a mind?")],
            current_href="guide/index.html",
            root="../",
        )
        self.assertIn('href="../questions/index.html"', nav)
        self.assertNotIn("All Questions", nav)
        self.assertNotIn("V1 Reader", nav)
        self.assertNotIn("Map", nav)
        self.assertNotIn("About", nav)
        self.assertNotIn("Archive", nav)
        self.assertNotIn("Audit Layer", nav)
        self.assertIn("Go Deeper", nav)
        self.assertIn("Further Reading", nav)
        self.assertIn("Glossary, Claims, Sources", nav)

    def test_mermaid_is_omitted_unless_enabled(self) -> None:
        md = "\n".join(
            [
                "```mermaid",
                "flowchart LR",
                "  A-->B",
                "```",
                "",
                "After.",
                "",
            ]
        )
        html_body, _text = build_site.blocks_to_html(build_site.parse_blocks(md), sources={}, root="./")
        self.assertNotIn("flowchart", html_body)
        self.assertIn("After.", html_body)


if __name__ == "__main__":
    unittest.main()
