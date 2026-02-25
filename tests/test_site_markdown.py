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
        self.assertEqual(blocks[0].anchors, (("yt_abc", "00:01:02"), ("ccc_def", "00:03:04")))

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
        self.assertEqual(blocks[0].anchors, (("yt_abc", "00:01:02"),))

    def test_linkifies_claim_and_term_ids(self) -> None:
        md = "See CLM-0001 and TERM-0002.\n"
        html_body, _text = build_site.blocks_to_html(build_site.parse_blocks(md), sources={}, root="./")
        self.assertIn('href="./claims/index.html#clm-0001"', html_body)
        self.assertIn('href="./glossary/index.html#term-0002"', html_body)

    def test_claims_have_deterministic_ids(self) -> None:
        md = "## CLM-0001: Foo\n\nBar\n"
        html_body, _text = build_site.blocks_to_html(build_site.parse_blocks(md), sources={}, root="./", page_kind="claims")
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
        html_body, _text = build_site.blocks_to_html(build_site.parse_blocks(md), sources={}, root="./", page_kind="glossary")
        self.assertIn('id="term-0001"', html_body)
        self.assertIn('id="term-0002"', html_body)

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

